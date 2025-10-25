import cv2
from cvzone.HandTrackingModule import HandDetector
from time import time
from pynput.keyboard import Controller, Key
import re  # Import regex for word separation

# --- Camera and Detector Setup ---
# Initialize the webcam (0 is usually the built-in webcam)
cap = cv2.VideoCapture(0)
# Set the default window resolution for the visual interface
cap.set(3, 1280)  # Width
cap.set(4, 720)  # Height

# Initialize the hand detector to allow for two-hand detection
# 'detectionCon=0.8' sets the confidence threshold for detection
detector = HandDetector(detectionCon=0.7, maxHands=2)

# --- AI Feature: Prediction Dictionary ---
PREDICTION_WORDS = [
    "THE", "AND", "THAT", "HAVE", "FOR", "NOT", "WITH", "YOU", "BUT", "THIS",
    "FROM", "WAS", "ARE", "GET", "CAN", "WHAT", "WHEN", "OUT", "BECAUSE", "JUST",
    "WORK", "CODE", "PYTHON", "PROJECT", "GEMINI", "VIRTUAL", "KEYBOARD", "Dr.DEVA PRIYA,Mohan"
]

# Landmark ID for the index fingertip
FINGER_TIPS = [8]

# --- MODIFIED: Accuracy & Cooldown Tuning ---
# Z-movement thresholds for detecting tap down and tap release.
# These values have been increased to require a more deliberate press, improving accuracy.
Z_DOWN_MOVEMENT = -15  # Finger must move towards the camera by at least 15 units.
Z_UP_MOVEMENT = 15   # Finger must move away from the camera by at least 15 units to register the press.

# Cooldown period in seconds to prevent accidental presses when moving the finger.
KEY_PRESS_COOLDOWN = 0.9


def predict_word(current_fragment):
    """
    Finds the best word suggestion based on the current word fragment.
    """
    if not current_fragment:
        return ""

    # Filter and sort words starting with the fragment (case-insensitive)
    suggestions = [
        word for word in PREDICTION_WORDS
        if word.startswith(current_fragment.upper())
    ]

    # Return the best suggestion or an empty string if none are found
    return suggestions[0] if suggestions else ""


# --- Keyboard Layout ---
# Define the keys on the virtual keyboard.
keys = [["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
        ["A", "S", "D", "F", "G", "H", "J", "K", "L", ";"],
        ["Z", "X", "C", "V", "B", "N", "M", ",", ".", "/"],
        ["SPACE", "DELETE"]]

# --- Variables ---
# String to hold the final typed text
finalText = ""
# Controller to simulate key presses to the operating system
keyboard = Controller()
# A dictionary to track the state of each hand for deliberate key presses
hand_states = {}
# A variable to track the last swipe action time to avoid repeated deletion
last_swipe_time = 0
# Dictionary to store key-specific states for visual feedback (color, time)
key_feedback = {}
# Window Title is kept for cv2.imshow
WINDOW_TITLE = "AI Virtual Keyboard (Finger Depth Tap to Type)"
# State to track if the keyboard input is ready after showing 5 fingers
is_keyboard_active = False
# NEW: Tracks the time of the last successful key press for cooldown
last_key_press_time = 0


# --- Button Class ---
# A class to represent each key on the virtual keyboard
class Button():
    def __init__(self, pos, text, size=[85, 85]):
        self.pos = pos
        self.size = size
        self.text = text


# --- Create Button Objects ---
# Create a list of Button objects for each key
buttonList = []
x_padding = 50
y_padding = 50
x_spacing = 100
y_spacing = 100

# Define the final positions for DELETE and calculate SPACE width
SCREEN_WIDTH = 1280
GAP = 10
RIGHT_EDGE_PADDING = 50

# Total usable width for the SPACE and DELETE buttons in the last row
TOTAL_USABLE_WIDTH = SCREEN_WIDTH - x_padding - RIGHT_EDGE_PADDING

# Width available for the buttons themselves (Total usable width minus the gap between them)
BUTTONS_TOTAL_WIDTH = TOTAL_USABLE_WIDTH - GAP

# NEW SIZING LOGIC: 50% for SPACE, 50% for DELETE
SPACE_WIDTH = int(BUTTONS_TOTAL_WIDTH * 0.50)
DELETE_WIDTH = BUTTONS_TOTAL_WIDTH - SPACE_WIDTH

# X coordinate where the DELETE button starts
X_DELETE_START = x_padding + SPACE_WIDTH + GAP

for i in range(len(keys)):
    for j, key in enumerate(keys[i]):

        # Calculate Y position for the current row
        y_pos = y_spacing * i + y_padding

        if key == "SPACE":
            # Use the calculated 50% width for the spacebar
            buttonList.append(Button([x_padding, y_pos], key, size=[SPACE_WIDTH, 85]))
        elif key == "DELETE":
            # Position DELETE based on the calculated start position and 50% width
            buttonList.append(Button([X_DELETE_START, y_pos], key, size=[DELETE_WIDTH, 85]))
        else:
            # Normal character keys
            buttonList.append(Button([x_spacing * j + x_padding, y_pos], key))

        key_feedback[key] = {"color": (0, 255, 0), "start_time": 0}  # Initialize key feedback state


# --- Drawing Function ---
def drawAll(img, buttonList, prediction_text, is_active):
    """Function to draw all the buttons, prediction, and instructions."""

    # 1. Draw all keyboard buttons
    for button in buttonList:
        x, y = button.pos
        w, h = button.size

        # Check if the key's color should revert to green
        if time() - key_feedback[button.text]["start_time"] > 0.2:  # Revert after 0.2 seconds
            key_feedback[button.text]["color"] = (0, 255, 0)

        # Get the color for the key from the feedback state
        color = key_feedback[button.text]["color"]

        # Draw the rectangle with the current color and a border for better look
        cv2.rectangle(img, button.pos, (x + w, y + h), color, cv2.FILLED)
        cv2.rectangle(img, button.pos, (x + w, y + h), (0, 0, 0), 2)  # Black border

        # Draw the text
        if button.text == "SPACE" or button.text == "DELETE":
            cv2.putText(img, button.text, (x + 20, y + 65), cv2.FONT_HERSHEY_PLAIN, 3, (255, 255, 255), 3)
        else:
            cv2.putText(img, button.text, (x + 20, y + 65), cv2.FONT_HERSHEY_PLAIN, 4, (255, 255, 255), 4)

    # 3. Activation Status
    status_text = "ACTIVE: Typing Enabled (Finger Tap Down/Up)" if is_active else "INACTIVE: Open Hand to Activate"
    status_color = (0, 255, 0) if is_active else (0, 165, 255)  # Green when active, Orange when inactive

    cv2.putText(img, status_text, (50, 40),
                cv2.FONT_HERSHEY_DUPLEX, 1, status_color, 2)

    # 2. Draw Prediction Suggestion
    if prediction_text:
        # Prediction bar position (just above the typed text)
        pred_x, pred_y = 50, 430
        pred_w = 550
        pred_h = 50

        # Draw a semi-transparent background for the suggestion
        overlay = img.copy()
        cv2.rectangle(overlay, (pred_x, pred_y), (pred_x + pred_w, pred_y + pred_h), (50, 50, 50), cv2.FILLED)
        alpha = 0.5
        img = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)

        # Draw the prediction text (in yellow)
        cv2.putText(img, f"Suggestion: {prediction_text} (Make a Fist to Accept)", (pred_x + 10, pred_y + 35),
                    cv2.FONT_HERSHEY_DUPLEX, 1, (0, 255, 255), 2)

    return img


# --- Main Application Loop ---
while True:
    # Read a frame from the webcam
    success, img = cap.read()
    if not success:
        print("Failed to read from camera.")
        break

    # Flip the image horizontally for a more natural mirror-like view
    img = cv2.flip(img, 1)

    # --- Hand Detection ---
    # Find up to two hands in the current frame
    hands, img = detector.findHands(img, flipType=False)

    # --- AI Prediction Logic ---
    words = re.split(r'\s+', finalText.strip())
    current_word = words[-1] if words and finalText.strip() else ""
    suggestion = predict_word(current_word)

    # --- Hand Processing ---
    if hands:
        for hand in hands:
            lmList = hand["lmList"]
            hand_type = hand["type"]

            if hand_type not in hand_states:
                # Initialize state tracking for the hand
                hand_states[hand_type] = {
                    "swipe_start_x": None,
                    "was_fist": False,
                    "finger_z_history": {},  # Tracks last Z position for all tips
                }
                # Initialize Z history and tapped state for each finger
                for tip_id in FINGER_TIPS:
                    # Initialize Z-history with current Z-position
                    hand_states[hand_type]["finger_z_history"][tip_id] = lmList[tip_id][2]
                    # Initialize tap-down state
                    hand_states[hand_type][f'is_down_{tip_id}'] = False

            # Get the state of all 5 fingers (1=Up, 0=Down)
            fingers = detector.fingersUp(hand)

            # --- Activation: 5 Fingers Open (Required to start typing) ---
            if fingers == [1, 1, 1, 1, 1]:
                is_keyboard_active = True

            # --- 1. "Tap" Detection (Finger Depth Movement for Keypress) ---
            if is_keyboard_active:
                key_pressed = False

                # Check for tap detection using Z-coordinate movement
                for tip_id in FINGER_TIPS:
                    finger_x, finger_y, finger_z = lmList[tip_id]  # Current (x, y, z)

                    # Ensure we have a previous Z value to compare against
                    if tip_id not in hand_states[hand_type]["finger_z_history"]:
                        hand_states[hand_type]["finger_z_history"][tip_id] = finger_z
                        continue

                    prev_z = hand_states[hand_type]["finger_z_history"][tip_id]
                    z_movement = finger_z - prev_z  # Negative means moving towards camera (down)

                    is_tapped_down = hand_states[hand_type].get(f'is_down_{tip_id}', False)

                    # Tapped Down: Finger moved significantly closer
                    if z_movement < Z_DOWN_MOVEMENT:
                        hand_states[hand_type][f'is_down_{tip_id}'] = True

                    # Tap Release: Finger moved significantly away AND was previously down
                    elif is_tapped_down and z_movement > Z_UP_MOVEMENT:
                        # --- NEW: Cooldown Check ---
                        # Only proceed if the cooldown period has passed since the last press.
                        if time() - last_key_press_time > KEY_PRESS_COOLDOWN:
                            # Register keypress only on the release (upward motion)
                            hand_states[hand_type][f'is_down_{tip_id}'] = False

                            # Check if this finger tip is over a key
                            for button in buttonList:
                                x, y = button.pos
                                w, h = button.size

                                # Check if the current fingertip is over the key
                                if x < finger_x < x + w and y < finger_y < y + h:
                                    # Visual Feedback
                                    key_feedback[button.text]["color"] = (128, 0, 128)  # Purple
                                    key_feedback[button.text]["start_time"] = time()

                                    # Handle keypress simulation (targets active window)
                                    if button.text == "SPACE":
                                        keyboard.press(Key.space)
                                        keyboard.release(Key.space)
                                        finalText += " "
                                    elif button.text == "DELETE":
                                        keyboard.press(Key.backspace)
                                        keyboard.release(Key.backspace)
                                        if len(finalText) > 0:
                                            finalText = finalText[:-1]
                                    else:
                                        keyboard.press(button.text.lower())
                                        keyboard.release(button.text.lower())
                                        finalText += button.text

                                    key_pressed = True
                                    # --- NEW: Update the cooldown timer ---
                                    last_key_press_time = time()
                                    break  # Exit button loop after a key is pressed
                            if key_pressed:
                                break  # Exit fingertip loop if a key was pressed
                        else:
                            # If we are in the cooldown period, still reset the 'is_down' state.
                            # This prevents a key from being pressed automatically once the cooldown ends
                            # without a new, explicit tap gesture.
                            hand_states[hand_type][f'is_down_{tip_id}'] = False

                    # Update Z history for the next frame
                    hand_states[hand_type]["finger_z_history"][tip_id] = finger_z

            # --- 2. AI Prediction Selection Gesture (Fist/5 Fingers Closed) ---
            is_fist_now = fingers == [0, 0, 0, 0, 0]

            if is_fist_now and not hand_states[hand_type]["was_fist"]:
                hand_states[hand_type]["was_fist"] = True
                if suggestion:
                    if current_word in finalText:
                        suggestion_to_type = suggestion[len(current_word):] + " "
                        keyboard.type(suggestion_to_type)
                        finalText = finalText.rsplit(current_word, 1)[0] + suggestion + " "
                    is_keyboard_active = False
            elif not is_fist_now:
                hand_states[hand_type]["was_fist"] = False

            # --- 3. Swipe to Delete All (Targets Active Window) ---
            if hand_type == "Right":
                current_x = hand["lmList"][0][0]
                if hand_states[hand_type]["swipe_start_x"] is None:
                    if current_x > 640:
                        hand_states[hand_type]["swipe_start_x"] = current_x
                else:
                    swipe_distance = hand_states[hand_type]["swipe_start_x"] - current_x
                    if swipe_distance > 400 and (time() - last_swipe_time) > 1.0:
                        keyboard.press(Key.ctrl)
                        keyboard.press('a')
                        keyboard.release('a')
                        keyboard.release(Key.ctrl)
                        keyboard.press(Key.backspace)
                        keyboard.release(Key.backspace)
                        finalText = ""
                        last_swipe_time = time()
                        cv2.putText(img, "Cleared!", (500, 400), cv2.FONT_HERSHEY_DUPLEX, 3, (0, 0, 255), 5)
                    elif swipe_distance < -100: # Reset if hand moves back
                        hand_states[hand_type]["swipe_start_x"] = None


    # Draw all the keys and the prediction onto the image
    img = drawAll(img, buttonList, suggestion, is_keyboard_active)

    # --- Display Typed Text ---
    cv2.rectangle(img, (50, 500), (1230, 600), (0, 255, 0), cv2.FILLED)
    cv2.putText(img, finalText, (60, 580), cv2.FONT_HERSHEY_PLAIN, 5, (255, 255, 255), 5)

    # --- Show the Final Image ---
    cv2.imshow(WINDOW_TITLE, img)

    # Process display events and check for exit key 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the camera and destroy all windows when the loop ends
cap.release()
cv2.destroyAllWindows()
