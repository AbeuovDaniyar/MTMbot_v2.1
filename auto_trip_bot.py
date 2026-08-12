from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, ElementNotInteractableException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import time
import os
import random
import traceback
import sys

class TripDetailsBot:
    def __init__(self, driver_path=None, profile_path=None):
        """Initialize the bot with Chrome webdriver and persistent profile option"""
        
        # --- CONFIGURATION: Driver & Vehicle Pairs (UPDATED) ---
        self.driver_vehicle_map = {
            # Mapping driver name to the unique 5-digit Vehicle ID
            "Mark Allamy": "12791",
            "Alexis Novella": "01965",
            "Kelby Infante": "15799",
            "Joseph Figueroa": "11884",
            "Alfred Rivera-ruiz": "85327"
        }
        # ---------------------------------------------

        # Set to keep track of processed trip numbers to avoid duplicates
        self.processed_trips = set()

        self.driver = None 
        
        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-extensions')
        
        # ⭐️ PERSISTENT PROFILE LOGIC ⭐️
        if profile_path:
            profile_path = os.path.abspath(profile_path)
            os.makedirs(profile_path, exist_ok=True) 
            options.add_argument(f'--user-data-dir={profile_path}')
            options.add_argument('--profile-directory=Default') 
            print(f"Using persistent Chrome profile at: {profile_path}")
        # ⭐️ END PERSISTENT PROFILE LOGIC ⭐️

        options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        try:
            if driver_path:
                from selenium.webdriver.chrome.service import Service
                service = Service(driver_path)
                self.driver = webdriver.Chrome(service=service, options=options)
            else:
                self.driver = webdriver.Chrome(options=options)
            
            # Set a default explicit wait timeout (e.g., 10 seconds)
            self.wait = WebDriverWait(self.driver, 10) 
            
        except Exception as e:
            print(f"FATAL ERROR during driver initialization: {e}")
            raise e

    # --- Time parsing and helper methods (omitted for brevity) ---
    def parse_time(self, time_str):
        try:
            time_str = time_str.strip()
            if 'AM' in time_str.upper() or 'PM' in time_str.upper():
                time_obj = time.strptime(time_str.upper(), '%I:%M %p')
            else:
                time_obj = time.strptime(time_str, '%H:%M')
            return time_obj.tm_hour * 60 + time_obj.tm_min
        except: return None

    def minutes_to_time(self, minutes):
        minutes = minutes % (24 * 60)
        hour = minutes // 60
        minute = minutes % 60
        return f"{hour:02d}:{minute:02d}"

    def time_to_12hour_format(self, time_24):
        try:
            parts = time_24.split(':')
            hour_24 = int(parts[0])
            minute = parts[1]
            if hour_24 == 0: hour_12, ampm = 12, 'am'
            elif hour_24 < 12: hour_12, ampm = hour_24, 'am'
            elif hour_24 == 12: hour_12, ampm = 12, 'pm'
            else: hour_12, ampm = hour_24 - 12, 'pm'
            return {'hour': str(hour_12), 'minute': minute, 'ampm': ampm}
        except: return None

    def add_random_minutes(self, base_time, min_offset, max_offset):
        base_minutes = self.parse_time(base_time)
        if base_minutes is None: return base_time
        random_offset = random.randint(min_offset, max_offset)
        return self.minutes_to_time(base_minutes + random_offset)
    
    def get_current_driver(self):
        try:
            driver_spans = self.driver.find_elements(By.XPATH, "//input[@id='driverIdStr']/ancestor::div[contains(@class, 'ant-select')]//span[contains(@class, 'ant-select-selection-item')]")
            if driver_spans and driver_spans[0].is_displayed():
                text = driver_spans[0].text.strip()
                return text if text else "None"
            return "None"
        except Exception:
            return "None"

    def get_current_vehicle(self):
        try:
            vehicle_spans = self.driver.find_elements(By.XPATH, "//input[@id='vehicleIdStr']/ancestor::div[contains(@class, 'ant-select')]//span[contains(@class, 'ant-select-selection-item')]")
            if vehicle_spans and vehicle_spans[0].is_displayed():
                text = vehicle_spans[0].text.strip()
                return text if text else "None"
            return "None"
        except Exception:
            return "None"

    def get_current_signature_status(self):
        return "Present" if self.has_signature() else "None"

    def get_scheduled_pickup_time(self):
        try:
            time_input = self.driver.find_element(By.NAME, "scheduledPickTime")
            time_value = time_input.get_attribute('value')
            if not time_value or time_value.strip() == '': return None
            return time_value.strip()
        except: return None

    def get_pickup_arrive_time(self):
        try:
            val = self.driver.find_element(By.NAME, "reportedPickArrive").get_attribute('value')
            return val.strip() if val else None
        except: return None
    
    def get_time_field_value(self, field_name):
        try:
            val = self.driver.find_element(By.NAME, field_name).get_attribute('value')
            return val.strip() if val else None
        except:
            return "N/A"

    def is_time_difference_greater_than(self, time1, time2, minutes_threshold):
        t1, t2 = self.parse_time(time1), self.parse_time(time2)
        if t1 is None or t2 is None: return False
        return abs(t1 - t2) > minutes_threshold

    def click_edit_button(self, trip_number):
        """Finds and clicks the edit button for a trip, then waits for the form to open."""
        try:            
            # OPTIMIZATION: Combine all selectors into a single XPath query using '|' (OR).
            # This allows Selenium to find the button in one attempt, avoiding cumulative wait times.
            combined_xpath = (
                f"//tr[.//td[contains(text(), '{trip_number}')]]//button[.//i[contains(@class, 'editIcon')]] | "
                f"//td[contains(text(), '{trip_number}')]/ancestor::tr//*[contains(@class, 'editIcon')] | "
                f"//td[contains(text(), '{trip_number}')]/ancestor::tr//td[last()]//button"
            )

            # Wait for the first element matching any of the selectors to be clickable.
            # The total wait time is now a maximum of 10 seconds, not 30.
            edit_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, combined_xpath)))
            
            # Use a JavaScript click, which can be faster and more reliable.
            self.driver.execute_script("arguments[0].click();", edit_button)
            
            # Wait for the form to open by checking for a known element inside it.
            self.wait.until(EC.presence_of_element_located((By.NAME, "scheduledPickTime")))
            print("✓ Edit button clicked and form is open.")
            return True

        except TimeoutException:
            print(f"❌ Could not find or click the edit button for trip {trip_number} within the time limit.")
            return False
        except Exception as e:
            print(f"⚠️ Error clicking edit button or waiting for form: {e}")
            return False

    def fill_time_field(self, field_label, field_name, time_value):
        try:
            tp = self.time_to_12hour_format(time_value)
            if not tp: return False
            container = self.driver.find_element(By.XPATH, f"//input[@name='{field_name}']/ancestor::div[contains(@class, 'react-time-picker')]")
            h = container.find_element(By.XPATH, ".//input[@name='hour12']")
            h.clear(); h.send_keys(tp['hour'])
            m = container.find_element(By.XPATH, ".//input[@name='minute']")
            m.clear(); m.send_keys(tp['minute'])
            Select(container.find_element(By.XPATH, ".//select[@name='amPm']")).select_by_value(tp['ampm'])
            return True
        except Exception as e:
            print(f"Error filling {field_label}: {e}")
            return False

    def has_signature(self):
        """
        Checks for signature presence.
        """
        try:
            # CHECK 1: The Negative Indicator (Text for Missing Signature)
            missing_text_xpath = "//*[contains(text(), 'Please do not upload multiple signatures for one claim')]"
            missing_elements = self.driver.find_elements(By.XPATH, missing_text_xpath)
            
            if missing_elements and missing_elements[0].is_displayed():
                return False
                
            # CHECK 2: The Positive Indicator (Clear/Re-sign Button)
            clear_button_xpath = "//button[contains(text(), 'Clear') or contains(text(), 'Re-sign')]"
            clear_buttons = self.driver.find_elements(By.XPATH, clear_button_xpath)
            
            if clear_buttons and clear_buttons[0].is_displayed():
                return True
            
            # Fallback check for visible, non-empty canvas
            canvas = self.driver.find_elements(By.XPATH, "//canvas") 
            if len(canvas) > 0:
                js_check = """
                var canvas = arguments[0];
                var ctx = canvas.getContext('2d');
                var data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
                for(var i = 0; i < data.length; i += 4) {
                    if (data[i] !== 0 || data[i+1] !== 0 || data[i+2] !== 0 || data[i+3] !== 0) {
                        return true;
                    }
                }
                return false;
                """
                for c in canvas:
                    try:
                        if self.driver.execute_script(js_check, c):
                            return True
                    except:
                        continue
                        
            return False
            
        except Exception as e: 
            print(f"Error checking signature: {e}")
            return False 

    def select_driver(self):
        """
        Selects a driver by first shuffling the preferred list and then searching for them one by one.
        This is efficient for virtualized lists as it stops on the first match.
        """
        try:
            # 1. Get the list of preferred drivers and shuffle it for random selection.
            preferred_drivers = list(self.driver_vehicle_map.keys())
            random.shuffle(preferred_drivers)

            # 2. Open the driver dropdown.
            driver_select_container = self.wait.until(EC.presence_of_element_located(
                (By.XPATH, "//input[@id='driverIdStr']/ancestor::div[contains(@class, 'ant-select')]")
            ))
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", driver_select_container)
            ActionChains(self.driver).move_to_element(driver_select_container).click().perform()
            
            dropdown_xpath = "//div[contains(@class, 'ant-select-dropdown') and not(contains(@class, 'ant-select-dropdown-hidden'))]"
            self.wait.until(EC.visibility_of_element_located((By.XPATH, dropdown_xpath)))
            scroll_container_xpath = f"{dropdown_xpath}//div[contains(@class, 'rc-virtual-list-holder')]"
            scroll_container = self.wait.until(EC.presence_of_element_located((By.XPATH, scroll_container_xpath)))

            # 3. Iterate through the SHUFFLED list to find the first available driver.
            for driver_to_find in preferred_drivers:
                print(f"→ Searching for driver: {driver_to_find}...")
                # Reset scroll to the top for each new search.
                self.driver.execute_script("arguments[0].scrollTop = 0;", scroll_container)
                time.sleep(0.2)

                last_scroll_top = -1
                while True:
                    try:
                        # Try to find the driver in the current view.
                        driver_option = scroll_container.find_element(By.XPATH, f".//div[contains(@class, 'ant-select-item-option-content') and normalize-space(.)='{driver_to_find}']")
                        
                        # If found, get the clickable parent, click it, and return.
                        clickable_element = driver_option.find_element(By.XPATH, "./ancestor::div[contains(@class, 'ant-select-item-option')]")
                        self.driver.execute_script("arguments[0].click();", clickable_element)
                        print(f"✓ Selected driver: **{driver_to_find}**")
                        return driver_to_find

                    except NoSuchElementException:
                        # Driver not visible, so scroll down.
                        self.driver.execute_script("arguments[0].scrollTop += arguments[0].clientHeight;", scroll_container)
                        time.sleep(0.3) # Pause for items to render.

                        current_scroll_top = self.driver.execute_script("return arguments[0].scrollTop;", scroll_container)
                        if current_scroll_top == last_scroll_top:
                            # Reached the end of the list for this driver, break to try the next one.
                            print(f"  - Reached end of list, '{driver_to_find}' not found.")
                            break
                        last_scroll_top = current_scroll_top
            
            # 4. FALLBACK: If the loop finishes, no preferred drivers were found. Select a random one.
            print("⚠️ None of the preferred drivers were found. Selecting a random driver from the list.")
            
            # Reset scroll to the top to read all drivers
            self.driver.execute_script("arguments[0].scrollTop = 0;", scroll_container)
            time.sleep(0.3)

            all_drivers = {}
            last_scroll_top = -1
            while True:
                options = scroll_container.find_elements(By.XPATH, ".//div[contains(@class, 'ant-select-item-option-content')]")
                for opt in options:
                    try:
                        driver_name = opt.text.strip()
                        if driver_name and driver_name not in all_drivers:
                            all_drivers[driver_name] = opt
                    except StaleElementReferenceException:
                        continue

                self.driver.execute_script("arguments[0].scrollTop += arguments[0].clientHeight;", scroll_container)
                time.sleep(0.3)
                current_scroll_top = self.driver.execute_script("return arguments[0].scrollTop;", scroll_container)
                if current_scroll_top == last_scroll_top:
                    break # Reached the end of the list
                last_scroll_top = current_scroll_top

            if not all_drivers:
                print("❌ Dropdown is empty. Could not select any driver.")
                return None

            random_driver_name = random.choice(list(all_drivers.keys()))
            random_driver_element = all_drivers[random_driver_name].find_element(By.XPATH, "./ancestor::div[contains(@class, 'ant-select-item-option')]")
            self.driver.execute_script("arguments[0].click();", random_driver_element)
            print(f"✓ Selected random driver: **{random_driver_name}**")
            return random_driver_name

        except Exception as e:
            print(f"Error selecting driver: {e}")
            return None

    def select_vehicle(self, driver_name):
        """
        Selects the mapped vehicle ID using stabilized incremental scroll and fixed delays.
        """
        try:
            target_vehicle = self.driver_vehicle_map.get(driver_name)
            
            # 1. Locate and Click Vehicle Dropdown Container
            vehicle_select_container = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//input[@id='vehicleIdStr']/ancestor::div[contains(@class, 'ant-select')]")
            ))
            
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", vehicle_select_container)
            time.sleep(0.5) # Increased sleep to allow UI to settle after scroll
            ActionChains(self.driver).move_to_element(vehicle_select_container).click().perform()
            
            # 2. Wait for Options to be Visible and get scrolling container
            dropdown_xpath = "//div[contains(@class, 'ant-select-dropdown') and not(contains(@class, 'ant-select-dropdown-hidden'))]"
            self.wait.until(EC.visibility_of_element_located((By.XPATH, dropdown_xpath)))
            scroll_container_xpath = f"{dropdown_xpath}//div[contains(@class, 'rc-virtual-list-holder')]"
            
            scroll_container = self.wait.until(EC.presence_of_element_located((By.XPATH, scroll_container_xpath)))
            
            # --- FIX: Ensure scroll starts from the top ---
            self.driver.execute_script("arguments[0].scrollTop = 0;", scroll_container)
            time.sleep(0.2) # Brief pause to allow UI to update after scroll

            # --- STABILIZED SCROLL AND READ LOGIC FOR VEHICLES (with fixed sleep) ---
            all_vehicles = {}
            found_vehicle_element = None
            last_scroll_top = -1
            
            while True:
                options = self.driver.find_elements(By.XPATH, f"{dropdown_xpath}//div[contains(@class, 'ant-select-item-option')]")
                
                for opt in options:
                    try:
                        option_text = self.driver.execute_script("return arguments[0].innerText;", opt).strip()
                        
                        if option_text and option_text not in all_vehicles:
                            all_vehicles[option_text] = opt
                            
                            if target_vehicle.strip() in option_text:
                                found_vehicle_element = opt
                    except StaleElementReferenceException:
                        continue
                
                if found_vehicle_element:
                    break 

                self.driver.execute_script("arguments[0].scrollTop += arguments[0].clientHeight;", scroll_container)
                time.sleep(0.3)
                current_scroll_top = self.driver.execute_script("return arguments[0].scrollTop;", scroll_container)
                if current_scroll_top == last_scroll_top:
                    break
                last_scroll_top = current_scroll_top
            # --- END STABILIZED SCROLL AND READ LOGIC ---

            selected_element = found_vehicle_element
            
            # 3. Final Check and Click
            if selected_element is None:
                # FALLBACK: If mapped vehicle not found, select a random one.
                print(f"⚠️ Mapped vehicle ID '**{target_vehicle}**' not found. Selecting a random vehicle.")
                if not all_vehicles:
                    print("❌ Dropdown is empty. Could not select any vehicle.")
                    return False
                
                random_vehicle_text = random.choice(list(all_vehicles.keys()))
                selected_element = all_vehicles[random_vehicle_text]
                print(f"✓ Selecting random vehicle: **{random_vehicle_text}**")
            else:
                print(f"✓ Mapped vehicle **{target_vehicle}** found.")

            # 4. Scroll and Click the chosen one using robust methods (JS Click)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'});", selected_element)
            time.sleep(0.1) 
            
            self.driver.execute_script("arguments[0].click();", selected_element)
            
            # 🚨 REVERTED: Using fixed time.sleep(0.5)
            time.sleep(0.5) 
            
            return True
            
        except Exception as e:
            print(f"Error selecting vehicle (Phase 1): {e}")
            return False

    def display_changes_and_confirm(self, trip_number, original_data, new_data):
        """Displays original vs. new data and prompts user for manual confirmation."""
        
        max_label_len = max(len(k) for k in new_data.keys())
        format_str = f"  {{:<{max_label_len}}} | {{:<15}} → {{}}"
        
        print(f"\n{'='*70}")
        print(f"REVIEW CHANGES FOR TRIP: {trip_number}")
        print(f"{'='*70}")
        print(f"  {'Field':<{max_label_len}} | {'Original Value':<15} → New Value")
        print(f"{'-'*(max_label_len + 35)}")
        
        for field, new_value in new_data.items():
            original_value = original_data.get(field, "N/A")

            # Convert None to a displayable string before formatting to prevent TypeError.
            display_original = original_value if original_value is not None else "N/A"
            display_new = new_value if new_value is not None else "N/A"
            
            if field == "Signature Status":
                print(format_str.format(field, display_original, display_new))
            elif original_value != new_value and original_value != "N/A":
                print(format_str.format(field, display_original, f"**{display_new}**"))
            else:
                print(format_str.format(field, display_original, display_new))
                
        print(f"{'='*70}")

        # The confirmation prompt is removed for full automation.
        # The script will now automatically proceed with saving.
        print("✓ Auto-confirming changes. Proceeding with save...")
        return True

    def upload_signature(self, file_path):
        try:
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                return False
            
            file_input_xpath = "//input[@type='file']"
            
            try:
                file_input = self.wait.until(EC.presence_of_element_located((By.XPATH, file_input_xpath)))
            except TimeoutException:
                print("Error: Could not find <input type='file'> element.")
                return False

            self.driver.execute_script("arguments[0].style.display = 'block'; arguments[0].style.visibility = 'visible';", file_input)
            
            file_input.send_keys(os.path.abspath(file_path))
            
            time.sleep(1) 
            
            self.driver.execute_script("arguments[0].style.display = 'none';", file_input)

            print(f"✓ Signature path sent directly to hidden input: {file_path}")
            return True
            
        except Exception as e:
            print(f"Error handling signature upload input: {e}")
            return False

    def save_changes(self):
        try:
            save_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Save Changes')]")))
            # Use a JavaScript click as a robust alternative if the standard click is flaky.
            self.driver.execute_script("arguments[0].click();", save_button)

            # --- IMPROVED WAIT LOGIC ---
            # 1. Wait for the loading spinner to appear and then disappear. This confirms the save action was processed.
            self.wait.until(EC.invisibility_of_element_located((By.XPATH, "//div[contains(@class, 'ant-spin-spinning')]")))

            # 2. Wait for the edit form/modal to close. This is a reliable indicator that the UI is back to the main view.
            self.wait.until(EC.invisibility_of_element_located((By.XPATH, "//div[contains(@class, 'ant-drawer-mask') or contains(@class, 'ant-modal-mask')]")))

            print("✓ Changes saved successfully.")
            return True
            
        except Exception as e:
            print(f"Error saving changes: {e}")
            return False

    def cancel_edit(self):
        try:
            cancel_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Cancel')]")))
            cancel_button.click()
            # Still keeping explicit wait for modal/drawer to disappear
            self.wait.until(EC.invisibility_of_element_located((By.XPATH, "//div[contains(@class, 'ant-modal-mask') or contains(@class, 'ant-drawer-mask')]")))
        except:
            try: self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except: pass

    def process_trip(self, trip_number, signature_path):
        print(f"\n=== Processing Trip: {trip_number} ===")
        
        if not self.click_edit_button(trip_number):
            print(f"⚠️ Skipping trip {trip_number}: Could not open edit form")
            # No need to cancel if it never opened
            return False
        
        # --- STEP 1: READ ORIGINAL VALUES ---
        original_data = {
            "Driver": self.get_current_driver(),
            "Vehicle": self.get_current_vehicle(),
            "Signature Status": "Present" if self.has_signature() else "Missing",
            "Scheduled Pickup": self.get_scheduled_pickup_time(), 
            "Pickup Arrive": self.get_time_field_value("reportedPickArrive"),
            "Pickup Depart": self.get_time_field_value("reportedPickPerform"),
            "Dropoff Arrive": self.get_time_field_value("reportedDropArrive"),
            "Dropoff Completion": self.get_time_field_value("reportedDropPerform"),
        }
        
        scheduled_pickup = original_data.get("Scheduled Pickup")
        if not scheduled_pickup:
            print("❌ Could not read scheduled pickup time. Skipping trip.")
            print("❌ Could not read 'Scheduled Pickup' time. Skipping trip.")
            self.cancel_edit()
            return False
        
        # --- STEP 2: APPLY CHANGES (TIME, DROPDOWNS, SIGNATURE) ---
        
        # 2a. Time Fields
        current_pickup_arrive = original_data["Pickup Arrive"]
        if current_pickup_arrive in (None, "N/A") or self.is_time_difference_greater_than(current_pickup_arrive, scheduled_pickup, 15):
            pickup_arrive = self.add_random_minutes(scheduled_pickup, -10, 10)
        else:
            pickup_arrive = current_pickup_arrive
        
        pickup_depart = self.add_random_minutes(pickup_arrive, 2, 10)
        dropoff_arrive = self.add_random_minutes(pickup_depart, 10, 30)
        dropoff_completion = self.add_random_minutes(dropoff_arrive, 0, 3)
        
        self.fill_time_field("Pickup Arrive", "reportedPickArrive", pickup_arrive)
        self.fill_time_field("Pickup Depart", "reportedPickPerform", pickup_depart)
        self.fill_time_field("Dropoff Arrive", "reportedDropArrive", dropoff_arrive)
        self.fill_time_field("Dropoff Completion", "reportedDropPerform", dropoff_completion)
        
        
        # 2b. Driver/Vehicle Selection
        selected_driver = original_data["Driver"]
        
        # Only select a new driver if one isn't set or isn't in our map
        if selected_driver == "None" or selected_driver not in self.driver_vehicle_map:
            selected_driver = self.select_driver()

        if selected_driver and selected_driver in self.driver_vehicle_map:
            # Only select a vehicle if the current one doesn't match the target
            if not self.select_vehicle(selected_driver):
                self.cancel_edit()
                return False
        elif selected_driver:
            print(f"⚠️ Driver '{selected_driver}' not mapped. Skipping trip for safety.")
            self.cancel_edit()
            return False
        else:
            print("❌ Driver selection failed or no driver selected. Skipping trip.")
            self.cancel_edit()
            return False
        
        selected_vehicle = self.get_current_vehicle()
        # Re-fetch vehicle only if it was changed
        selected_vehicle = self.get_current_vehicle() 
        
        # 2c. Signature Upload (PRE-CONFIRMATION)
        is_sig_present = self.has_signature()
        sig_status_for_confirm = original_data["Signature Status"]
        
        if not is_sig_present:
            if self.upload_signature(signature_path):
                sig_status_for_confirm = "**Uploaded Successfully**"
            else:
                sig_status_for_confirm = "**Upload FAILED**"
        
        # --- STEP 3: USER CONFIRMATION (Original vs. New) ---
        new_data = {
            "Scheduled Pickup": original_data["Scheduled Pickup"], 
            "Pickup Arrive": pickup_arrive,
            "Pickup Depart": pickup_depart,
            "Dropoff Arrive": dropoff_arrive,
            "Dropoff Completion": dropoff_completion,
            "Driver": selected_driver,
            "Vehicle": selected_vehicle,
            "Signature Status": sig_status_for_confirm 
        }
        
        confirmation_result = self.display_changes_and_confirm(trip_number, original_data, new_data)
        
        # --- STEP 4: SAVE OR CANCEL ---
        if confirmation_result is True:
            self.save_changes()
            print(f"✓ Trip {trip_number} completed successfully\n")
            return True
        else:
            # If user cancels or skips
            self.cancel_edit()
            print(f"→ Trip {trip_number} changes reverted.\n")
            if confirmation_result == 'skip':
                print(f"→ Trip {trip_number} skipped by user.\n")
            else:
                print(f"→ Trip {trip_number} changes reverted by user.\n")
            return False

    def get_all_trip_numbers_from_table(self):
        try:
            # This more specific XPath targets the 4th column of the table body, which reliably contains the trip number.
            # It finds all `tr` elements within the `tbody` and then selects the 4th `td` child.
            trip_cells_xpath = "//tbody[contains(@class, 'ant-table-tbody')]/tr/td[4]"
            
            # Wait for at least one trip number to be present to ensure the table has loaded.
            self.wait.until(EC.presence_of_element_located((By.XPATH, trip_cells_xpath)))
            
            # Find all elements matching the specific XPath.
            trip_cells = self.driver.find_elements(By.XPATH, trip_cells_xpath)
            
            # Extract the text, ensuring it starts with 'C0' and remove duplicates.
            return list(dict.fromkeys([cell.text.strip() for cell in trip_cells if cell.text.strip().startswith('C0')]))
        except: return []
    
    def process_all_pages(self, signature_path):
        """Processes all trips across all pages in the table."""
        page_number = 1
        while True:
            print(f"\n{'='*20} Processing Page {page_number} {'='*20}")
            
            # Get all trip numbers on the current page
            trip_numbers_on_page = self.get_all_trip_numbers_from_table()
            if not trip_numbers_on_page:
                print("No more trips found on this page.")
                break

            # Filter out trips that have already been processed
            trips_to_process = [trip for trip in trip_numbers_on_page if trip not in self.processed_trips]

            if not trips_to_process:
                print("All trips on this page have already been processed.")
            else:
                print(f"Found {len(trips_to_process)} new trips to process on this page.")
                for i, trip_number in enumerate(trips_to_process, 1):
                    print(f"\n--- Processing trip {i} of {len(trips_to_process)} on page {page_number} ---")
                    if self.process_trip(trip_number, signature_path):
                        self.processed_trips.add(trip_number)
                    time.sleep(1)

            # After processing the page, try to go to the next one
            try:
                next_button = self.driver.find_element(By.CSS_SELECTOR, "li.ant-pagination-next:not(.ant-pagination-disabled) button")
                print("\nNavigating to the next page...")
                self.driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3) # Wait for the next page to load
                page_number += 1
            except (NoSuchElementException, TimeoutException):
                print("\nNo more pages to process. Automation complete.")
                break

    def close(self):
        if self.driver: self.driver.quit()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

if __name__ == "__main__":
    # ⭐️ CONFIGURATION: PERSISTENT PROFILE PATH ⭐️
    # Use the folder the exe/script lives in (not cwd) so the profile always lands
    # next to the exe regardless of where the user launches it from.
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    PERSISTENT_PROFILE_PATH = os.path.join(app_dir, 'Selenium_Automation_Profile')

    # DYNAMIC DRIVER: driver_path is left as None on purpose.
    # Selenium 4.6+ ships "Selenium Manager", which auto-detects the user's
    # installed Chrome version and downloads a matching chromedriver on the
    # fly (cached in %LOCALAPPDATA%\selenium afterward). This avoids the
    # "chromedriver version doesn't match Chrome" failure that happens when
    # Chrome auto-updates past a bundled driver. Requires internet access on
    # first run (or whenever Chrome updates); after that it uses the cache.
    bot = TripDetailsBot(driver_path=None, profile_path=PERSISTENT_PROFILE_PATH) 
    
    try:
        bot.driver.get("https://mtm.mtmlink.net/pe/v1/claims") # Make sure this is the correct URL
        
        # 🔑 PROMPT: Pause execution for manual login/navigation
        input("Press Enter after logging in (if necessary) and navigating to the trips page...")
        
        time.sleep(2)
        # Use the resource_path helper to find the signature file
        # This assumes 'signature.png' will be in the same folder as the .exe
        signature_file = resource_path("signature.png")
        bot.process_all_pages(signature_file)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        
    finally:
        try: input("Press Enter to close browser...")
        except: pass
        bot.close()