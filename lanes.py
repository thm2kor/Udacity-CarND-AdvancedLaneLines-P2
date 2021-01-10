import numpy as np
import cv2
import config
# class to receive the characteristics of each line detection
class line():
    def __init__(self, id=""):
        self.id = id
        # was the line detected in the last iteration?
        self.detected = False
        # x values of the last n fits of the line
        self.recent_xfitted = []
        #x values of the fitted line over the last n iterations
        self.bestx = None
        #polynomial coefficients averaged over the last n iterations
        self.best_fit = None
        #polynomial coefficients for the last n number of runs
        self.current_fit = []
        #recent calculated polynomial coefficients
        self.recent_fit = None
        #radius of curvature of the line in some units
        self.radius_of_curvature = None
        #distance in meters of vehicle center from the line
        self.line_base_pos = None
        #difference in fit coefficients between last and new fits
        self.diffs = np.array([0,0,0], dtype='float')
        #number of detected pixels
        self.px_count = None ## unused
        #color of the line
        self.color = (255, 255, 0)
        #thickness of the line
        self.thickness = 15
        #weights for average
        self.ranking = []
        #y values for detected line pixels
        self.ally = []
        #x values for detected line pixels
        self.allx = []

    ## calculate the radis of curvature
    def calc_curavture(self, ym_per_pix, xm_per_pix ):
        ploty = np.linspace(0, (config.IMAGE_HEIGHT)-1, config.IMAGE_HEIGHT)
        #fit a second degree polynomial, which fits the current x and y points
        fit_cr = np.polyfit((self.ally * ym_per_pix), (self.allx * xm_per_pix), 2)
        #fit a second degree polynomial, which fits the current x and y points
        y_eval = np.max(ploty)*ym_per_pix

        self.radius_of_curvature = ((1 + (2*fit_cr[0]*y_eval + fit_cr[1])**2)**1.5)/abs(2*fit_cr[0])
        return self.radius_of_curvature

    # This function validates the "recent-fit" which was set by the 'track' object.
    # The line object saves the last n fits. If the incoming fit is deviating too much
    # from the last n fits, then the line rejects the fit and sets the internal state
    # 'detected' to false. This is an indication to the track object to re-scan
    # the lanes using the sliding window approach.
    def validate_recent_fit(self):
        # if the recent fit is valid.
        # The track object can invalidate the recent fit by setting it to None
        if self.recent_fit is not None:
            if self.best_fit is not None:
                # compare the recent fit with the best fit which is already available
                self.diffs = abs(self.recent_fit-self.best_fit)
            if  self.diffs[2] > 100.: # if the intercept (constant part) is longer than 100 pixels
                #print('detected bad fit..rejecting recent fit')
                self.detected = False
            else:
                self.detected = True
                # All ok. Add to the curent fit
                self.current_fit.append(self.recent_fit)
                ## Ranking of the current fit based on the number of detected pixels
                self.ranking.append(len(self.recent_xfitted))
                # Limit the array (current_fit and ranking ) limited to 'n'
                if len(self.current_fit) > 10: #keep the arrays(
                    self.current_fit = self.current_fit[len(self.current_fit)-10:]
                    self.ranking = self.ranking[len(self.ranking)-10:]
                #calculate bets fit as a weighted average of the current fits based on ranking matrix
                self.best_fit = np.average(self.current_fit, axis=0, weights=self.ranking)
        else:# No suitable fit from the last scan. keep the best fit as the average of the last n run
            self.detected = False
            if len(self.current_fit) > 0:
                self.best_fit = np.average(self.current_fit, axis=0, weights=self.ranking)

class drivingLane:
    def __init__(self) :
        self.leftline = line ('left')
        self.rightline = line ('right')
        self.detected = False
        self.width = 0.
        self.vehicle_pos = 0.
        ##From class notes Lesson 8 - Advanced Computer vision - Measuring Curvature -II
        ##"U.S. regulations require a minimum lane width of 12 feet or 3.7 meters,
        ## and the dashed lane lines are 10 feet or 3 meters long each."

        ## The above dimensions in world space is manually checked with an example warped
        ## image - straight_line1.jpg and straight_line2.jpg
        self.ym_per_pix = 3/110 	# 110 is the number of pixels for one lane segement in straight_line1_warped.jpg
        self.xm_per_pix = 3.7/380	# 380 is number of pixels for one lane width in straight_line1_warped.jpg


    def is_detected(self):
        return self.leftline.detected and self.rightline.detected

    def is_incoming_fit_valid(self):
        return self.leftline.incoming_fit is not None and self.rightline.incoming_fit is not None

    def get_curve_radius(self):
        return (self.leftline.calc_curavture(self.ym_per_pix, self.xm_per_pix) + \
                self.rightline.calc_curavture(self.ym_per_pix, self.xm_per_pix))/2

    #function compares the left lane and right lane at 3 identical y coordinates.
    #if the average difference of the left and right lane are within a certain range
    #then it can be detected that the lanes are parallel to each other
    def areLanesParallel(self):
        ret = True
        if self.leftline.recent_fit is not None and self.rightline.recent_fit is not None:
            widths = np.zeros(3) # calculate widths at top, mid and bottom of the frame (perspective transformed)

            ploty = np.linspace(0, config.IMAGE_WIDTH-1, num=config.IMAGE_WIDTH)# to cover same y-range as image
            left_fitx = self.leftline.recent_fit[0]*ploty**2 + self.leftline.recent_fit[1]*ploty + self.leftline.recent_fit[2]
            right_fitx = self.rightline.recent_fit[0]*ploty**2 + self.rightline.recent_fit[1]*ploty + self.rightline.recent_fit[2]

            if left_fitx is not None and right_fitx is not None:
                widths[0] = abs(right_fitx[0] - left_fitx[0])
                widths[1] = abs(right_fitx[int(max(ploty)/2)] - left_fitx[int(max(ploty)/2)])
                widths[2] = abs(right_fitx[int(max(ploty)-1)] - left_fitx[int(max(ploty)-1)])
                #print (widths)

            if max(widths) - min(widths) >= 100 : #TODO - Finetune the thresholds by running the challenge video
                ret = True

        return ret

    #function calculates the intercept and left and right lane
    #the difference of the intercept is the lane width.
    #if the lane width is longer than  width + offset, then
    #the lane is flagged as "wide"
    def areLanesTooWide(self):
        ret = False
        if self.leftline.recent_fit is not None and self.rightline.recent_fit is not None:
            #calculate the intercept of the recent fit for both line
            left_intercept = self.leftline.recent_fit[0]*config.IMAGE_HEIGHT**2 + self.leftline.recent_fit[1]*config.IMAGE_HEIGHT + self.leftline.recent_fit[2]
            right_intercept = self.rightline.recent_fit[0]*config.IMAGE_HEIGHT**2 + self.rightline.recent_fit[1]*config.IMAGE_HEIGHT + self.rightline.recent_fit[2]
            x_int_diff = abs(right_intercept-left_intercept)
            if x_int_diff > 480 : #(380 + offset of 100)
                ret = True
        return ret

    #trigger the calculation of the radius of curvature of the individual lines
    def calc_curvature(self):
        self.leftline.calc_curavture(self.ym_per_pix, self.xm_per_pix)
        self.rightline.calc_curavture(self.ym_per_pix, self.xm_per_pix)

    #calculation the vehicle position with respect to the lane
    def get_vehicle_pos(self, image_shape):
        ## Class notes -- You can assume the camera is mounted at the center of the car,
        ## such that the lane center is the midpoint at the bottom of the image
        ## between the two lines you've detected. The offset of the lane
        ## center from the center of the image (converted from pixels to meters)
        ##is your distance from the center of the lane.
        ## https://knowledge.udacity.com/questions/311566
        vehicle_position = image_shape[1]/2
        leftline_intercept = self.leftline.best_fit[0]*image_shape[0]**2 + self.leftline.best_fit[1]*image_shape[0] + self.leftline.best_fit[2]
        rightline_intercept = self.rightline.best_fit[0]*image_shape[0]**2 + self.rightline.best_fit[1]*image_shape[0] + self.rightline.best_fit[2]
        lane_center = (leftline_intercept + rightline_intercept) /2
        self.vehicle_pos = (vehicle_position - lane_center) * self.xm_per_pix
        return self.vehicle_pos

    #Function that detects potential lane lines from an warped, binary thresholded
    #image.
    def detect_lines(self, edges):
        if not self.is_detected():
            # attempts the find a set of lines based on "sliding windows method"
            self.find_new_fit(edges)
        else:
            # find the lane around the points detected from the previous function
            self.follow_prev_fit(edges)
        # validity check at track level for the recently detected lane
        if not self.areLanesParallel() or self.areLanesTooWide():
            # rejecting the lanes incase they are not plausible
            self.leftline.recent_fit = None
            self.rightline.recent_fit = None
        # validity check at line level
        self.leftline.validate_recent_fit()
        self.rightline.validate_recent_fit()

    # Finding a lane based on the sliding windows  method.
    # code taken over from Lesson : Finding the Lines: Sliding Window
    # Chapter 8: Advanced Computer Vision
    # from Udacity Nanodegree program :
    # Minor modifications done for encapsulating the function inside a class
    def find_new_fit(self, img):
        # Take a histogram of the bottom half of the image
        histogram = np.sum(img[img.shape[0]//2:,:], axis=0)
        # Find the peak of the left and right halves of the histogram
        # These will be the starting point for the left and right lines
        midpoint = np.int(histogram.shape[0]//2)
        #quarter_point = np.int(midpoint//2)
        # Previously the left/right base was the max of the left/right half of the histogram
        # this changes it so that only a quarter of the histogram (directly to the left/right) is considered
        leftx_base = np.argmax(histogram[:midpoint])
        rightx_base = np.argmax(histogram[midpoint:]) + midpoint
        # Choose the number of sliding windows
        nwindows = 10
        # Set height of windows
        window_height = np.int(img.shape[0]/nwindows)
        # Identify the x and y positions of all nonzero pixels in the image
        nonzero = img.nonzero()
        nonzeroy = np.array(nonzero[0])
        nonzerox = np.array(nonzero[1])
        # Current positions to be updated for each window
        leftx_current = leftx_base
        rightx_current = rightx_base
        # Set the width of the windows +/- margin
        margin = 80
        # Set minimum number of pixels found to recenter window
        minpix = 30
        # Create empty lists to receive left and right lane pixel indices
        left_lane_inds = []
        right_lane_inds = []
        # Step through the windows one by one
        for window in range(nwindows):
            # Identify window boundaries in x and y (and right and left)
            win_y_low = img.shape[0] - (window+1)*window_height
            win_y_high = img.shape[0] - window*window_height
            win_xleft_low = leftx_current - margin
            win_xleft_high = leftx_current + margin
            win_xright_low = rightx_current - margin
            win_xright_high = rightx_current + margin
            # Identify the nonzero pixels in x and y within the window
            good_left_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) & (nonzerox >= win_xleft_low) & (nonzerox < win_xleft_high)).nonzero()[0]
            good_right_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) & (nonzerox >= win_xright_low) & (nonzerox < win_xright_high)).nonzero()[0]
            # Append these indices to the lists
            left_lane_inds.append(good_left_inds)
            right_lane_inds.append(good_right_inds)
            # If you found > minpix pixels, recenter next window on their mean position
            if len(good_left_inds) > minpix:
                leftx_current = np.int(np.mean(nonzerox[good_left_inds]))
            if len(good_right_inds) > minpix:
                rightx_current = np.int(np.mean(nonzerox[good_right_inds]))

        # Concatenate the arrays of indices
        left_lane_inds = np.concatenate(left_lane_inds)
        right_lane_inds = np.concatenate(right_lane_inds)

        # Extract left and right line pixel positions
        leftx = nonzerox[left_lane_inds]
        lefty = nonzeroy[left_lane_inds]
        rightx = nonzerox[right_lane_inds]
        righty = nonzeroy[right_lane_inds]

        # Fit a second order polynomial to each
        if len(leftx) != 0:
            self.leftline.recent_xfitted = leftx
            self.leftline.allx = leftx
            self.leftline.ally=lefty
            self.leftline.recent_fit = np.polyfit(lefty, leftx, 2)
            self.leftline.detected = True
        else:
            self.leftline.recent_fit = None
            #print ('left lane not found')

        if len(rightx) != 0:
            self.rightline.recent_xfitted = rightx
            self.rightline.allx = rightx
            self.rightline.ally = righty
            self.rightline.recent_fit = np.polyfit(righty, rightx, 2)
            self.rightline.detected = True
        else:
            self.rightline.recent_fit = None
            #print ('right lane not found')

    # Tracking a line based on the previous selected fit.
    # code taken over from Lesson : Finding the Lines: Search from Prior
    # Chapter 8: Advanced Computer Vision
    # Minor modifications done for encapsulating the function inside a class
    def follow_prev_fit(self,binary_warped):
        #print ('tracking lane')
        nonzero = binary_warped.nonzero()
        nonzeroy = np.array(nonzero[0])
        nonzerox = np.array(nonzero[1])

        margin = 80

        left_lane_inds = ((nonzerox > (self.leftline.recent_fit[0]*(nonzeroy**2) + self.leftline.recent_fit[1]*nonzeroy + self.leftline.recent_fit[2] - margin)) &
                          (nonzerox < (self.leftline.recent_fit[0]*(nonzeroy**2) + self.leftline.recent_fit[1]*nonzeroy + self.leftline.recent_fit[2] + margin)))
        right_lane_inds = ((nonzerox > (self.rightline.recent_fit[0]*(nonzeroy**2) + self.rightline.recent_fit[1]*nonzeroy + self.rightline.recent_fit[2] - margin)) &
                           (nonzerox < (self.rightline.recent_fit[0]*(nonzeroy**2) + self.rightline.recent_fit[1]*nonzeroy + self.rightline.recent_fit[2] + margin)))

        # Again, extract left and right line pixel positions
        leftx = nonzerox[left_lane_inds]
        lefty = nonzeroy[left_lane_inds]
        rightx = nonzerox[right_lane_inds]
        righty = nonzeroy[right_lane_inds]

        if len(leftx) != 0:
            # Fit a second order polynomial to each
            self.leftline.recent_xfitted = leftx
            self.leftline.ally = lefty
            self.leftline.allx = leftx
            self.leftline.recent_fit = np.polyfit(lefty, leftx, 2)
        if len(rightx) != 0:
            self.rightline.recent_xfitted = rightx
            self.rightline.ally = righty
            self.rightline.allx = rightx
            self.rightline.recent_fit = np.polyfit(righty, rightx, 2)


    def overlay_lanes(self, original, overlay):
        #new_img = np.copy(original_img)
        if self.leftline.best_fit is None or self.rightline.best_fit is None:
            print('overlay_lanes - receiving empty fits..')
            return original
        # Create an image to draw the lines on
        warp_zero = np.zeros_like(overlay).astype(np.uint8)
        color_warp = np.dstack((warp_zero, warp_zero, warp_zero))

        ploty = np.linspace(0, overlay.shape[0]-1, num=overlay.shape[0])# to cover same y-range as image
        left_fitx = self.leftline.best_fit[0]*ploty**2 + self.leftline.best_fit[1]*ploty + self.leftline.best_fit[2]
        right_fitx = self.rightline.best_fit[0]*ploty**2 + self.rightline.best_fit[1]*ploty + self.rightline.best_fit[2]

        # Recast the x and y points into usable format for cv2.fillPoly()
        pts_left = np.array([np.transpose(np.vstack([left_fitx, ploty]))])
        pts_right = np.array([np.flipud(np.transpose(np.vstack([right_fitx, ploty])))])
        pts = np.hstack((pts_left, pts_right))

        # Draw the lane onto the warped blank image
        cv2.fillPoly(color_warp, np.int_([pts]), (0,255, 0))
        cv2.polylines(color_warp, np.int32([pts_left]), isClosed=False, color=self.leftline.color, thickness=self.leftline.thickness)
        cv2.polylines(color_warp, np.int32([pts_right]), isClosed=False, color=self.rightline.color, thickness=self.rightline.thickness)

        return color_warp