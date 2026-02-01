# 🛠️ ECE Attendance System: Feature Guide

This guide is for team members who want to understand exactly how the system works. It's written in simple terms for beginners.

## 1. Smart QR Scanning 📸
The system uses the `html5-qrcode` library to turn your browser into a scanner. 
*   **How it works**: When a QR code is scanned, the roll number is sent to our server.
*   **Automatic Check**: The server checks if the student is already in our database.
    *   If **Yes**: It marks them present for "Today".
    *   If **No**: It opens a friendly pop-up to ask for their name.

## 2. Auto-Registration (New Students) 🆕
If a student's roll number isn't found, the system doesn't error out. Instead, it asks for their name.
*   **Ease of Use**: Once you enter the name, the system adds them to the database **and** marks them present at the same time. No extra steps needed!

## 3. Real-Time Syncing (Socket.io) ⚡
We use a technology called **WebSockets**.
*   **The Benefit**: When one admin scans a student, the "Total Present" count updates on **every** admin's screen simultaneously. You don't need to refresh the page to see the latest stats.

## 4. Automatic Branch Detection 🔍
The system is "smart" enough to know a student's branch just from their Roll Number.
*   **Example**: If a roll number contains `05`, the system knows it's **CSE**. If it's `04`, it's **ECE**. 
*   This happens automatically without the student having to tell us their department.

## 5. Reports & Data Export 📄
Need to share the data? We have two powerful options:
*   **PDF Exports**: Get a clean, formatted list of attendees for specific departments (e.g., just the CSE students).
*   **Full Excel Data**: Download every detail of every student present today in a spreadsheet format for further analysis.

## 6. Duplicate Prevention 🛡️
To keep our data clean, the system ensures a student can only be marked present **once per day**. If you scan the same person twice, a warning message will let you know.

---
*Built with Python (Flask), MongoDB, and modern Web Technologies.*