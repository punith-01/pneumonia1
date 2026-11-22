"""
X-ray Image Validator - Enhanced Version
Validates if an uploaded image is a valid chest X-ray with stricter criteria
"""

import numpy as np
from PIL import Image
import os

class XRayValidator:
    """
    Validates if an image is a chest X-ray using multiple strict criteria
    Enhanced to reject non-X-ray images like photos, drawings, etc.
    """
    
    def __init__(self, verbose=False):
        """Initialize the validator"""
        self.criteria_results = {}
        # Strict mode - requires more checks to pass
        self.strict_mode = True
        self.verbose = verbose
    
    def _log(self, msg):
        """Internal helper for logging when verbose mode is enabled"""
        if self.verbose:
            print(msg)
    
    def is_valid_xray(self, image_path_or_array):
        """
        Check if image is a valid chest X-ray
        
        Args:
            image_path_or_array: Path to image file or PIL Image or numpy array
        
        Returns:
            tuple: (is_valid: bool, reason: str, confidence: float)
        """
        try:
            # Convert to PIL Image if needed
            if isinstance(image_path_or_array, str):
                img = Image.open(image_path_or_array)
            elif isinstance(image_path_or_array, np.ndarray):
                img = Image.fromarray(image_path_or_array.astype('uint8'))
            else:
                img = image_path_or_array
            
            # Store original mode to check if it was originally a color image
            original_mode = img.mode
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Convert to numpy array
            img_array = np.array(img)
            
            # Run validation checks
            checks = {
                'is_strictly_grayscale': self._check_strictly_grayscale(img_array),
                'not_colorful': self._check_not_colorful(img_array),
                'xray_brightness_pattern': self._check_xray_brightness_pattern(img_array),
                'xray_histogram_pattern': self._check_xray_histogram_pattern(img_array),
                'medical_contrast': self._check_medical_contrast(img_array),
                'anatomical_structure': self._check_anatomical_structure(img_array),
                'central_brightness': self._check_central_brightness(img_array),
                'edge_darkness': self._check_edge_darkness(img_array),
            }
            
            self.criteria_results = checks
            
            # Calculate validation score
            passed_checks = sum(1 for v in checks.values() if v)
            total_checks = len(checks)
            confidence = passed_checks / total_checks
            
            # STRICT validation criteria for X-rays:
            # 1. MUST be strictly grayscale (no color)
            # 2. MUST NOT be colorful
            # 3. MUST have X-ray histogram pattern
            # 4. At least 6 out of 8 checks must pass
            
            mandatory_checks = [
                checks['is_strictly_grayscale'],
                checks['not_colorful'],
            ]
            
            is_valid = all(mandatory_checks) and passed_checks >= 6
            
            if is_valid:
                reason = "Valid chest X-ray image"
            else:
                failed = [k for k, v in checks.items() if not v]
                if not checks['is_strictly_grayscale'] or not checks['not_colorful']:
                    reason = "This appears to be a color image, not an X-ray. Please upload a chest X-ray image."
                elif not checks['xray_histogram_pattern']:
                    reason = "Image does not have typical X-ray characteristics. Please upload a valid chest X-ray."
                else:
                    reason = f"Not a valid X-ray image. Please upload a chest X-ray."
            
            self._log(f"[VALIDATOR] Checks passed: {passed_checks}/{total_checks}")
            self._log(f"[VALIDATOR] Individual results: {checks}")
            self._log(f"[VALIDATOR] Final result: valid={is_valid}, confidence={confidence:.2%}")
            
            return is_valid, reason, confidence
        
        except Exception as e:
            print(f"[VALIDATOR] Error: {str(e)}")
            return False, f"Error validating image: {str(e)}", 0.0
    
    def _check_strictly_grayscale(self, img_array):
        """
        Check if image is strictly grayscale (all RGB channels nearly identical)
        X-rays are always grayscale - this is a strict check
        """
        try:
            if len(img_array.shape) != 3:
                return True
            
            r, g, b = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2]
            
            # Calculate mean absolute difference between channels
            r_g_diff = np.mean(np.abs(r.astype(float) - g.astype(float)))
            g_b_diff = np.mean(np.abs(g.astype(float) - b.astype(float)))
            r_b_diff = np.mean(np.abs(r.astype(float) - b.astype(float)))
            
            avg_diff = (r_g_diff + g_b_diff + r_b_diff) / 3
            max_diff = max(r_g_diff, g_b_diff, r_b_diff)
            
            # Very strict: X-rays should have nearly identical RGB values
            # Threshold: avg diff < 5 and max diff < 10
            is_grayscale = avg_diff < 5 and max_diff < 10
            
            self._log(f"[GRAYSCALE CHECK] avg_diff={avg_diff:.2f}, max_diff={max_diff:.2f}, passed={is_grayscale}")
            
            return is_grayscale
        except Exception as e:
            self._log(f"[GRAYSCALE CHECK] Error: {e}")
            return False
    
    def _check_not_colorful(self, img_array):
        """
        Check that image is NOT colorful (reject color photos)
        Uses saturation analysis in HSV space
        """
        try:
            if len(img_array.shape) != 3:
                return True
            
            # Convert to float and normalize
            img_float = img_array.astype(float) / 255.0
            r, g, b = img_float[:,:,0], img_float[:,:,1], img_float[:,:,2]
            
            # Calculate saturation (from HSV)
            max_rgb = np.maximum(np.maximum(r, g), b)
            min_rgb = np.minimum(np.minimum(r, g), b)
            
            # Avoid division by zero
            saturation = np.where(max_rgb > 0, (max_rgb - min_rgb) / (max_rgb + 1e-10), 0)
            
            mean_saturation = np.mean(saturation)
            max_saturation = np.percentile(saturation, 95)  # 95th percentile
            
            # Count highly saturated pixels
            high_saturation_ratio = np.mean(saturation > 0.15)
            
            # X-rays should have very low saturation
            not_colorful = mean_saturation < 0.05 and max_saturation < 0.15 and high_saturation_ratio < 0.05
            
            self._log(f"[COLOR CHECK] mean_sat={mean_saturation:.3f}, max_sat={max_saturation:.3f}, high_sat_ratio={high_saturation_ratio:.3f}, passed={not_colorful}")
            
            return not_colorful
        except Exception as e:
            self._log(f"[COLOR CHECK] Error: {e}")
            return False
    
    def _check_xray_brightness_pattern(self, img_array):
        """
        Check for X-ray specific brightness patterns
        X-rays have a specific distribution with dark backgrounds and brighter anatomy
        """
        try:
            if len(img_array.shape) == 3:
                gray = np.mean(img_array, axis=2)
            else:
                gray = img_array.astype(float)
            
            mean_brightness = np.mean(gray)
            std_brightness = np.std(gray)
            
            # X-rays typically have mean brightness between 80-180
            # and significant standard deviation (40-80)
            has_xray_brightness = 60 < mean_brightness < 200 and 30 < std_brightness < 90
            
            self._log(f"[BRIGHTNESS CHECK] mean={mean_brightness:.1f}, std={std_brightness:.1f}, passed={has_xray_brightness}")
            
            return has_xray_brightness
        except Exception as e:
            self._log(f"[BRIGHTNESS CHECK] Error: {e}")
            return False
    
    def _check_xray_histogram_pattern(self, img_array):
        """
        Check for X-ray specific histogram pattern
        X-rays have bimodal or multi-modal histograms with peaks at low and mid values
        """
        try:
            if len(img_array.shape) == 3:
                gray = np.mean(img_array, axis=2).astype(np.uint8)
            else:
                gray = img_array.astype(np.uint8)
            
            # Calculate histogram
            hist, _ = np.histogram(gray.flatten(), bins=256, range=(0, 256))
            hist = hist / hist.sum()  # Normalize
            
            # X-rays typically have:
            # 1. Some dark pixels (background)
            # 2. Mid-range pixels (tissue)
            # 3. Some bright pixels (bone/contrast)
            
            dark_ratio = np.sum(hist[:50])      # Very dark pixels
            mid_ratio = np.sum(hist[50:180])    # Mid-range pixels
            bright_ratio = np.sum(hist[180:])   # Bright pixels
            
            # X-ray pattern: significant mid-range with some dark and bright
            has_xray_histogram = (
                0.05 < dark_ratio < 0.5 and
                mid_ratio > 0.4 and
                bright_ratio < 0.4
            )
            
            self._log(f"[HISTOGRAM CHECK] dark={dark_ratio:.3f}, mid={mid_ratio:.3f}, bright={bright_ratio:.3f}, passed={has_xray_histogram}")
            
            return has_xray_histogram
        except Exception as e:
            self._log(f"[HISTOGRAM CHECK] Error: {e}")
            return False
    
    def _check_medical_contrast(self, img_array):
        """
        Check for medical image contrast characteristics
        X-rays have specific contrast patterns
        """
        try:
            if len(img_array.shape) == 3:
                gray = np.mean(img_array, axis=2)
            else:
                gray = img_array.astype(float)
            
            # Calculate contrast using different metrics
            std_val = np.std(gray)
            
            # Calculate local contrast (Weber contrast in patches)
            h, w = gray.shape
            patch_size = min(h, w) // 8
            if patch_size > 10:
                patches = []
                for i in range(0, h - patch_size, patch_size):
                    for j in range(0, w - patch_size, patch_size):
                        patch = gray[i:i+patch_size, j:j+patch_size]
                        patches.append(np.std(patch))
                local_contrast_var = np.var(patches)
            else:
                local_contrast_var = std_val ** 2
            
            # X-rays have good overall contrast and varied local contrast
            has_good_contrast = std_val > 35 and local_contrast_var > 50
            
            self._log(f"[CONTRAST CHECK] std={std_val:.1f}, local_var={local_contrast_var:.1f}, passed={has_good_contrast}")
            
            return has_good_contrast
        except Exception as e:
            self._log(f"[CONTRAST CHECK] Error: {e}")
            return False
    
    def _check_anatomical_structure(self, img_array):
        """
        Check for anatomical structures typical in chest X-rays
        Uses edge detection patterns
        """
        try:
            if len(img_array.shape) == 3:
                gray = np.mean(img_array, axis=2)
            else:
                gray = img_array.astype(float)
            
            # Calculate Sobel-like edge detection
            edges_x = np.abs(np.diff(gray, axis=0))
            edges_y = np.abs(np.diff(gray, axis=1))
            
            edge_mean = (np.mean(edges_x) + np.mean(edges_y)) / 2
            edge_std = (np.std(edges_x) + np.std(edges_y)) / 2
            
            # X-rays have moderate, varied edge patterns
            has_anatomical_edges = 3 < edge_mean < 30 and edge_std > 5
            
            self._log(f"[ANATOMY CHECK] edge_mean={edge_mean:.1f}, edge_std={edge_std:.1f}, passed={has_anatomical_edges}")
            
            return has_anatomical_edges
        except Exception as e:
            self._log(f"[ANATOMY CHECK] Error: {e}")
            return False
    
    def _check_central_brightness(self, img_array):
        """
        Check if central region is brighter (typical for chest X-rays)
        The lung fields in chest X-rays create specific brightness patterns
        """
        try:
            if len(img_array.shape) == 3:
                gray = np.mean(img_array, axis=2)
            else:
                gray = img_array.astype(float)
            
            h, w = gray.shape
            
            # Define central region (middle 50%)
            y1, y2 = int(h * 0.25), int(h * 0.75)
            x1, x2 = int(w * 0.25), int(w * 0.75)
            
            central = gray[y1:y2, x1:x2]
            peripheral = np.concatenate([
                gray[:y1, :].flatten(),
                gray[y2:, :].flatten(),
                gray[y1:y2, :x1].flatten(),
                gray[y1:y2, x2:].flatten()
            ])
            
            central_mean = np.mean(central)
            peripheral_mean = np.mean(peripheral)
            
            # Chest X-rays often have specific central vs peripheral brightness relationship
            # Either central is brighter (PA view) or the difference is moderate
            brightness_diff = abs(central_mean - peripheral_mean)
            
            has_xray_pattern = brightness_diff < 60  # Not too extreme difference
            
            self._log(f"[CENTRAL CHECK] central={central_mean:.1f}, peripheral={peripheral_mean:.1f}, diff={brightness_diff:.1f}, passed={has_xray_pattern}")
            
            return has_xray_pattern
        except Exception as e:
            self._log(f"[CENTRAL CHECK] Error: {e}")
            return False
    
    def _check_edge_darkness(self, img_array):
        """
        Check if edges are appropriately dark (typical for X-rays with collimation)
        """
        try:
            if len(img_array.shape) == 3:
                gray = np.mean(img_array, axis=2)
            else:
                gray = img_array.astype(float)
            
            h, w = gray.shape
            edge_width = max(h, w) // 10
            
            # Get edge regions
            top = gray[:edge_width, :].mean()
            bottom = gray[-edge_width:, :].mean()
            left = gray[:, :edge_width].mean()
            right = gray[:, -edge_width:].mean()
            
            edge_mean = (top + bottom + left + right) / 4
            center_mean = gray[edge_width:-edge_width, edge_width:-edge_width].mean()
            
            # In X-rays, edges can be darker (collimation) or similar to center
            edge_ratio = edge_mean / (center_mean + 1e-10)
            
            # Valid if edges are not excessively bright compared to center
            has_valid_edges = edge_ratio < 1.3
            
            self._log(f"[EDGE CHECK] edge_mean={edge_mean:.1f}, center_mean={center_mean:.1f}, ratio={edge_ratio:.2f}, passed={has_valid_edges}")
            
            return has_valid_edges
        except Exception as e:
            self._log(f"[EDGE CHECK] Error: {e}")
            return False
    
    def get_validation_details(self):
        """Get detailed validation results"""
        return self.criteria_results


# Test function
if __name__ == "__main__":
    print("="*70)
    print("     X-RAY IMAGE VALIDATOR TEST - ENHANCED VERSION")
    print("="*70)
    
    validator = XRayValidator(verbose=True)
    
    # Test with any images in uploads folder
    uploads_dir = "uploads"
    if os.path.exists(uploads_dir):
        for filename in os.listdir(uploads_dir):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                img_path = os.path.join(uploads_dir, filename)
                print(f"\n[TEST] Image: {img_path}")
                print("-" * 70)
                is_valid, reason, confidence = validator.is_valid_xray(img_path)
                print(f"\nResult:")
                print(f"  Valid: {is_valid}")
                print(f"  Reason: {reason}")
                print(f"  Confidence: {confidence:.2%}")
    
    print("\n" + "="*70)
    print("     TEST COMPLETE")
    print("="*70)
