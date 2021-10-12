import os
from tqdm import tqdm
import numpy as np
import pandas as pd
import cv2
import time
import re
import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
from Face_Recog import Main_Model
from Face_Recog.commons import functions, distance as dst
from Face_Recog.detectors import FaceDetector

Threshold_setter = 0.5


def analysis(db_path, df, model_name='VGG-Face', detector_backend='opencv', distance_metric='cosine',
             source=0, time_threshold=5, frame_threshold=5):
    face_detector = FaceDetector.build_model(detector_backend)
    print("Detector backend is ", detector_backend)

    # ------------------------

    employees = []
    # check passed db folder exists
    if os.path.isdir(db_path) == True:
        for r, d, f in os.walk(db_path):  # r=root, d=directories, f = files
            for file in f:
                if ('.jpg' in file):
                    # exact_path = os.path.join(r, file)
                    exact_path = r + "/" + file
                    employees.append(exact_path)

    if len(employees) == 0:
        print("WARNING: There is no image in this path ( ", db_path, ") . Face recognition will not be performed.")

    if len(employees) > 0:
        model = Main_Model.build_model(model_name)
        print(model_name, " is built")

        input_shape = functions.find_input_shape(model)
        input_shape_x = input_shape[0];
        input_shape_y = input_shape[1]

        # tuned thresholds for model and metric pair
        threshold = dst.findThreshold(model_name, distance_metric)

    pivot_img_size = 112  # face recognition result image
    freeze = False
    face_detected = False
    face_included_frames = 0  # freeze screen if face detected sequantially 5 frames
    freezed_frame = 0
    tic = time.time()

    cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)  # webcam
    while (True):
        ret, img = cap.read()
        ret2, img2 = cap.read()
        if img is None:
            break
        raw_img = img.copy()
        if freeze == False:
            # faces stores list of detected_face and region pair
            faces = FaceDetector.detect_faces(face_detector, detector_backend, img, align=False)
            if len(faces) == 0:
                face_included_frames = 0
        else:
            faces = []
        detected_faces = []
        face_index = 0
        for face, (x, y, w, h) in faces:
            if w > 0:  # discard small detected faces
                face_detected = True
                if face_index == 0:
                    face_included_frames = face_included_frames + 1  # increase frame for a single face
                detected_faces.append((x, y, w, h))
                face_index = face_index + 1

        if face_detected == True and face_included_frames == frame_threshold and freeze == False:
            freeze = True
            base_img = raw_img.copy()
            detected_faces_final = detected_faces.copy()
            tic = time.time()

        if freeze == True:
            toc = time.time()
            if (toc - tic) < time_threshold:
                if freezed_frame == 0:
                    freeze_img = base_img.copy()
                    Fin_img = base_img.copy()
                    # freeze_img = np.zeros(resolution, np.uint8) #here, np.uint8 handles showing white area issue
                    for detected_face in detected_faces_final:
                        x = detected_face[0];
                        y = detected_face[1]
                        w = detected_face[2];
                        h = detected_face[3]
                        cv2.rectangle(Fin_img, (x, y), (x + w, y + h), (67, 67, 67),
                                      1)  # draw rectangle to main image

                        # apply deep learning for custom_face

                        custom_face = base_img[y:y + h, x:x + w]

                        # face recognition

                        custom_face = functions.preprocess_face(img=custom_face,
                                                                target_size=(input_shape_y, input_shape_x),
                                                                enforce_detection=False, detector_backend='opencv')

                        # check preprocess_face function handled
                        if custom_face.shape[1:3] == input_shape:
                            if df.shape[0] > 0:  # if there are images to verify, apply face recognition
                                img1_representation = model.predict(custom_face)[0, :]

                                def findDistance(row):
                                    distance_metric = row['distance_metric']
                                    img2_representation = row['embedding']

                                    distance = 1000  # initialize very large value
                                    if distance_metric == 'cosine':
                                        distance = dst.findCosineDistance(img1_representation, img2_representation)
                                    elif distance_metric == 'euclidean':
                                        distance = dst.findEuclideanDistance(img1_representation, img2_representation)
                                    elif distance_metric == 'euclidean_l2':
                                        distance = dst.findEuclideanDistance(dst.l2_normalize(img1_representation),
                                                                             dst.l2_normalize(img2_representation))

                                    return distance

                                df['distance'] = df.apply(findDistance, axis=1)
                                df = df.sort_values(by=["distance"])

                                candidate = df.iloc[0]
                                employee_name = candidate['employee']
                                best_distance = candidate['distance']
                                values_ = candidate[['employee', 'distance']].values
                                name = values_[0].split("\\")[-1].split("/")[0]
                                print(name)
                                if best_distance <= threshold - Threshold_setter:

                                    display_img = cv2.imread(employee_name)

                                    display_img = cv2.resize(display_img, (pivot_img_size, pivot_img_size))

                                    label = employee_name.split("/")[-1].replace(".jpg", "")
                                    label = re.sub('[0-9]', '', label)

                                    cv2.rectangle(Fin_img, (10, 10), (180, 50), (67, 67, 67), -10)
                                    cv2.putText(Fin_img, str("Unknown"), (20, 40),
                                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 1)

                cv2.rectangle(Fin_img, (10, 10), (180, 50), (67, 67, 67), -10)
                cv2.putText(Fin_img, str(name), (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                            1, (255, 255, 255), 1)
                ret, buffer = cv2.imencode('.jpg', Fin_img)
                frame = buffer.tobytes()
                freezed_frame = freezed_frame + 1
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

                freezed_frame = freezed_frame + 1
            else:
                face_detected = False
                face_included_frames = 0
                freeze = False
                freezed_frame = 0
        else:
            ret, buffer = cv2.imencode('.jpg', img)
            frame = buffer.tobytes()
            # change_feed == True
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        if cv2.waitKey(1) & 0xFF == ord('q'):  # press q to quit
            break
    # kill open cv things
    cap.release()
    cv2.destroyAllWindows()