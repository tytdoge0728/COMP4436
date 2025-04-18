# 🅿️ IoT-Based Smart Parking System

A real-time smart parking monitoring solution using **ESP32 microcontrollers**, **infrared (IR) sensors**, **ThingSpeak** for cloud data logging, and a **Python Flask web dashboard** for data visualization. This system was developed as part of the COMP4436 Artificial Intelligence of Things course at The Hong Kong Polytechnic University.

---

## 👤 Team Member

- **Name:** Chin Chun Hei Anson  
- **Student ID:** 213110187D  
- **Project Code:** COMP4436-25-P10

---

## 🚀 Project Overview

This project addresses parking inefficiencies by detecting real-time slot availability and displaying the results on a web interface. Infrared sensors connected to ESP32 boards detect vehicle presence and send updates to the ThingSpeak cloud every 30 seconds. A Flask-based backend retrieves, processes, and presents the data on a live dashboard. It also includes trend analysis and prepares the system for future AI/ML integration.

---

## 🛠️ Tech Stack

- **ESP32 Development Board**
- **Infrared Sensors (IR)**
- **ThingSpeak Cloud API**
- **Python Flask + Flask-SocketIO**
- **HTML / CSS / JavaScript**
- **Matplotlib / Plotly (for analytics)**
- **PowerShell / CMD for deployment**

---

## 🧩 System Design

### 📶 Data Flow Diagram

[IR Sensor] → [ESP32] → [ThingSpeak Cloud] → [Flask API] → [Web Dashboard]


### 🧠 Components

- **ESP32 + IR Sensor:**
  - Detects occupancy (1 = occupied, 0 = vacant)
  - Sends updates to ThingSpeak via HTTP GET

- **ThingSpeak:**
  - Stores real-time status in 6 fields
  - Visualizes historical graphs per slot

- **Flask Backend:**
  - `parking_webapp.py` fetches and processes the latest data
  - `parking_iot.py` analyzes historical trends and usage rates

- **Frontend Dashboard:**
  - Displays parking availability
  - Shows usage charts and dynamic analytics


## 📁 Project Structure

## ⚙️ Setup Instructions

### 🔧 Requirements

- Python 3.8+
- ESP32 Boards (x6)
- Infrared Sensors (x6)
- Wi-Fi Connection

### 🧪 Setup Virtual Environment

```bash
python -m venv venv
.\venv\Scripts\activate    # Windows
# or
source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt

python parking_webapp.py



