# CropGuard AI - Smart Crop Disease Detection System

## Overview

CropGuard AI is an AI-powered web application developed to help farmers identify crop diseases quickly and accurately. The system allows users to upload crop images, detects diseases using a trained YOLOv8 deep learning model, and provides detailed information about the detected disease along with treatment and prevention recommendations.

The application also includes an AI chatbot with multilingual support, enabling farmers to ask agriculture-related questions and receive real-time assistance in English, Kannada, and Hindi.

---

## Features

### User Authentication
- Secure user registration and login
- JWT-based authentication
- Forgot Password using Email OTP

### Crop Disease Detection
- Upload crop images
- AI-powered disease detection using YOLOv8
- Display detected disease with confidence score
- Fast and accurate predictions

### Disease Information
- Disease name
- Symptoms
- Causes
- Recommended treatments
- Preventive measures

### AI Chatbot
- Agriculture assistance
- Multilingual support (English, Kannada, Hindi)
- Farming guidance and recommendations

### User Dashboard
- View uploaded images
- Prediction history
- User profile management

---

## Tech Stack

### Frontend
- React.js
- HTML5
- CSS3
- JavaScript

### Backend
- Node.js
- Express.js

### Database
- MongoDB
- Mongoose

### Artificial Intelligence
- YOLOv8
- Python
- OpenCV
- Ultralytics
- Roboflow

### Authentication
- JWT (JSON Web Token)
- Gmail OTP Verification

---

## Installation

### Clone the Repository

```bash
git clone https://github.com/your-username/cropguard-ai.git
```

### Install Frontend Dependencies

```bash
cd client
npm install
```

### Install Backend Dependencies

```bash
cd server
npm install
```

### Install Python Dependencies

```bash
pip install ultralytics opencv-python flask torch torchvision
```


### Start the Backend Server

```bash
npm start
```

### Start the Frontend Application

```bash
npm start
```

### Run the AI Model

```bash
python predict.py
```

---

## Objectives

- Detect crop diseases at an early stage using Artificial Intelligence.
- Help farmers make informed decisions with accurate disease diagnosis.
- Provide treatment and preventive recommendations.
- Reduce crop losses and improve agricultural productivity.
- Offer an easy-to-use platform accessible from anywhere.

---

## Future Enhancements

- Real-time disease detection using a live camera.
- Mobile application for Android and iOS.
- Weather-based crop recommendations.
- Fertilizer recommendation system.
- Voice-enabled AI assistant.
- Offline prediction support.
- Integration with IoT sensors for smart farming.

---

## Developed By

**Vaishnavi Kudari**

Bachelor of Engineering (Computer Science)

KLE Technological University

---

## License

This project is developed for educational and learning purposes.
