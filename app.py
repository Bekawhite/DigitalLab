# Digi_Lab.py
"""
Digi_Lab Streamlit App
A Streamlit adaptation of your Flask lab-results system.
Features:
- SQLite via SQLAlchemy (file: lab_results.db)
- User registration (patient, doctor, lab_tech)
- Login (simple session using st.session_state)
- Patient/Doctor/LabTech dashboards
- Lab result upload (file saved to ./uploads)
- View & download lab result files (streamlit download button)
- Simple placeholders for SMS/email notifications
"""

import streamlit as st
from datetime import datetime
import os
import secrets
import hashlib
import io

# SQLAlchemy imports
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session
from werkzeug.security import generate_password_hash, check_password_hash

# For making placeholder SMS/API calls (unused in demo)
import requests

# ---------- Configuration ----------
BASE_DIR = os.getcwd()
DB_PATH = os.path.join(BASE_DIR, "lab_results.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'txt', 'doc', 'docx'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# SQLAlchemy engine & session
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()

# ---------- Models (mirror your Flask models) ----------
class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(256))
    user_type = Column(String(20), nullable=False)  # patient, doctor, lab_tech
    phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)

    # relationships
    patient_profile = relationship('Patient', back_populates='user', uselist=False, cascade='all, delete-orphan')
    doctor_profile = relationship('Doctor', back_populates='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"

class Patient(Base):
    __tablename__ = 'patient'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    gender = Column(String(10), nullable=False)
    address = Column(Text)
    emergency_contact = Column(String(20))

    user = relationship('User', back_populates='patient_profile')
    results = relationship('LabResult', back_populates='patient', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Patient {self.first_name} {self.last_name}>"

class Doctor(Base):
    __tablename__ = 'doctor'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    specialization = Column(String(100), nullable=False)
    license_number = Column(String(50), unique=True, nullable=False)
    hospital = Column(String(100))

    user = relationship('User', back_populates='doctor_profile')

    def __repr__(self):
        return f"<Doctor {self.first_name} {self.last_name}>"

class LabResult(Base):
    __tablename__ = 'lab_result'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patient.id'), nullable=False)
    test_type = Column(String(100), nullable=False)
    test_date = Column(DateTime, nullable=False)
    result_date = Column(DateTime, nullable=False)
    status = Column(String(20), default='pending')  # pending, completed, delivered
    file_path = Column(String(200))  # stored filename in uploads folder
    notes = Column(Text)
    lab_technician = Column(String(100))

    patient = relationship('Patient', back_populates='results')
    notifications = relationship('Notification', back_populates='lab_result', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<LabResult {self.test_type} for patient_id {self.patient_id}>"

class Notification(Base):
    __tablename__ = 'notification'
    id = Column(Integer, primary_key=True)
    lab_result_id = Column(Integer, ForeignKey('lab_result.id'), nullable=False)
    notification_type = Column(String(20), nullable=False)  # sms, email, portal
    sent_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default='sent')  # sent, delivered, failed
    recipient = Column(String(100), nullable=False)  # phone number or email

    lab_result = relationship('LabResult', back_populates='notifications')

    def __repr__(self):
        return f"<Notification for result {self.lab_result_id}>"

# Create tables
Base.metadata.create_all(bind=engine)

# ---------- Helper functions ----------
def db_session():
    return SessionLocal()

def allowed_file(filename: str):
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def unique_filename(filename: str):
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    salt = secrets.token_hex(6)
    name = f"{ts}_{salt}_{secure_filename(filename)}"
    return name

# secure_filename replacement (werkzeug's secure_filename isn't imported directly)
def secure_filename(filename: str):
    # minimal sanitization: remove path separators and spaces
    return filename.replace("/", "_").replace("\\", "_").replace(" ", "_")

def save_uploaded_file(uploaded_file):
    """
    uploaded_file: an object returned by st.file_uploader
    returns saved filename or raises ValueError
    """
    if uploaded_file is None:
        raise ValueError("No file provided.")
    filename = uploaded_file.name
    if not allowed_file(filename):
        raise ValueError("File type not allowed.")
    data = uploaded_file.read()
    if len(data) > MAX_CONTENT_LENGTH:
        raise ValueError("File too large.")
    fname = unique_filename(filename)
    path = os.path.join(UPLOAD_FOLDER, fname)
    with open(path, "wb") as f:
        f.write(data)
    return fname

def get_user_by_username(db, username):
    return db.query(User).filter(User.username == username).first()

def get_user_by_email(db, email):
    return db.query(User).filter(User.email == email).first()

def get_doctor_by_license(db, lic):
    return db.query(Doctor).filter(Doctor.license_number == lic).first()

def login_user_in_session(user_obj):
    st.session_state['user_id'] = user_obj.id
    st.session_state['username'] = user_obj.username
    st.session_state['user_type'] = user_obj.user_type

def logout_user_from_session():
    for k in ('user_id', 'username', 'user_type'):
        if k in st.session_state:
            del st.session_state[k]

def current_user(db):
    uid = st.session_state.get('user_id')
    if not uid:
        return None
    return db.query(User).get(uid)

# ---------- Streamlit UI -----------

st.set_page_config(page_title="Digi_Lab", layout="centered")
st.title("Digi_Lab — Digital Laboratory Results System (Demo)")

menu = ["Home", "Register", "Login", "Dashboard", "Upload Result", "Logout"]
if st.session_state.get('user_type') == 'doctor':
    menu = ["Home", "Dashboard", "Logout"]
elif st.session_state.get('user_type') == 'patient':
    menu = ["Home", "Dashboard", "Logout"]
elif st.session_state.get('user_type') == 'lab_tech':
    menu = ["Home", "Upload Result", "Dashboard", "Logout"]

choice = st.sidebar.selectbox("Menu", menu)

db = db_session()

# ---------- HOME ----------
if choice == "Home":
    st.header("Welcome to Digi_Lab")
    st.write("A lightweight demo of your lab results system, adapted for Streamlit.")
    st.info("This is a demo. For production use, add stronger authentication, secure uploads, and a production DB.")
    st.markdown("""
    **Features included**
    - Patient/Doctor/Lab Technician registration & login  
    - Patient dashboard: view and download your lab results  
    - Doctor dashboard: view all patient results  
    - Lab technician: upload result files (PDF, JPG, PNG, DOC/DOCX, TXT)  
    """)

# ---------- REGISTER ----------
elif choice == "Register":
    st.header("Register a new account")
    role = st.selectbox("Register as", ["patient", "doctor", "lab_tech"])
    with st.form(key="register_form"):
        username = st.text_input("Username", max_chars=80)
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        phone = st.text_input("Phone (optional)")

        if role == "patient":
            st.subheader("Patient details")
            first_name = st.text_input("First name")
            last_name = st.text_input("Last name")
            dob = st.date_input("Date of Birth")
            gender = st.selectbox("Gender", ["male", "female", "other"])
            address = st.text_area("Address")
            emergency_contact = st.text_input("Emergency contact")
        else:
            st.subheader("Professional details")
            first_name = st.text_input("First name")
            last_name = st.text_input("Last name")
            if role == "doctor":
                specialization = st.text_input("Specialization")
                license_number = st.text_input("License number")
                hospital = st.text_input("Hospital / Clinic (optional)")
            else:
                # lab_tech minimal info
                specialization = ""
                license_number = ""
                hospital = ""
        submitted = st.form_submit_button("Register")

    if submitted:
        if not username or not email or not password:
            st.error("Username, email and password are required.")
        else:
            # check uniqueness
            if get_user_by_username(db, username):
                st.error("Username already exists. Try another.")
            elif get_user_by_email(db, email):
                st.error("Email already exists. Try another.")
            elif role == "doctor" and get_doctor_by_license(db, license_number):
                st.error("License number already registered.")
            else:
                try:
                    user = User(username=username, email=email, user_type=role, phone=phone)
                    user.set_password(password)
                    db.add(user)
                    db.flush()  # to get user.id

                    if role == "patient":
                        patient = Patient(
                            user_id=user.id,
                            first_name=first_name,
                            last_name=last_name,
                            date_of_birth=dob,
                            gender=gender,
                            address=address,
                            emergency_contact=emergency_contact
                        )
                        db.add(patient)
                    elif role == "doctor":
                        doctor = Doctor(
                            user_id=user.id,
                            first_name=first_name,
                            last_name=last_name,
                            specialization=specialization,
                            license_number=license_number,
                            hospital=hospital
                        )
                        db.add(doctor)
                    # lab_tech only has user record

                    db.commit()
                    st.success("Registration successful! You can now login.")
                except Exception as e:
                    db.rollback()
                    st.error(f"Error during registration: {str(e)}")

# ---------- LOGIN ----------
elif choice == "Login":
    st.header("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        remember = st.checkbox("Remember me (session persists while browser tab open)")
        submitted = st.form_submit_button("Login")

    if submitted:
        user = get_user_by_username(db, username)
        if user and user.check_password(password):
            login_user_in_session(user)
            st.success(f"Welcome back, {user.username}!")
            # refresh page to change menu
            st.experimental_rerun()
        else:
            st.error("Login failed. Check username and password.")

# ---------- LOGOUT ----------
elif choice == "Logout":
    if st.session_state.get('user_id'):
        st.write(f"Logged in as: {st.session_state.get('username')} ({st.session_state.get('user_type')})")
        if st.button("Logout now"):
            logout_user_from_session()
            st.success("You have been logged out.")
            st.experimental_rerun()
    else:
        st.info("You are not logged in.")

# ---------- UPLOAD RESULT (Lab Technician) ----------
elif choice == "Upload Result":
    if not st.session_state.get('user_id') or st.session_state.get('user_type') != 'lab_tech':
        st.warning("Access denied. Only logged-in lab technicians can upload results.")
    else:
        st.header("Upload Lab Result")
        patients = db.query(Patient).order_by(Patient.first_name).all()
        if not patients:
            st.info("No patients in the system yet. Ask patients to register first.")
        with st.form("upload_form", clear_on_submit=False):
            patient_options = {f"{p.first_name} {p.last_name} (DOB {p.date_of_birth.isoformat()})": p.id for p in patients}
            selected_label = st.selectbox("Select patient", options=list(patient_options.keys()))
            patient_id = patient_options[selected_label]
            test_type = st.text_input("Test type (e.g., Blood Test, MRI)", "")
            test_date = st.date_input("Test date", value=datetime.utcnow().date())
            result_date = st.date_input("Result date", value=datetime.utcnow().date())
            notes = st.text_area("Notes (optional)")
            uploaded_file = st.file_uploader("Result file (PDF/JPG/PNG/DOC/DOCX/TXT)", type=list(ALLOWED_EXTENSIONS))
            submitted = st.form_submit_button("Upload Result")

        if submitted:
            try:
                if not test_type:
                    st.error("Test type is required.")
                elif uploaded_file is None:
                    st.error("Please select a result file to upload.")
                else:
                    saved_name = save_uploaded_file(uploaded_file)
                    lab_result = LabResult(
                        patient_id=patient_id,
                        test_type=test_type,
                        test_date=datetime.combine(test_date, datetime.min.time()),
                        result_date=datetime.combine(result_date, datetime.min.time()),
                        status="completed",
                        file_path=saved_name,
                        notes=notes,
                        lab_technician=st.session_state.get('username')
                    )
                    db.add(lab_result)
                    db.commit()

                    # Create a simple Notification record (placeholder)
                    # In a real system you'd call an SMS/email API here.
                    patient = db.query(Patient).get(patient_id)
                    # choose recipient as patient's phone if user has it; else patient's user email
                    recipient = patient.user.phone if patient.user and patient.user.phone else patient.user.email
                    notification = Notification(
                        lab_result_id=lab_result.id,
                        notification_type="portal",
                        status="sent",
                        recipient=recipient
                    )
                    db.add(notification)
                    db.commit()

                    st.success("Lab result uploaded successfully.")
            except Exception as e:
                db.rollback()
                st.error(f"Upload failed: {str(e)}")

# ---------- DASHBOARD ----------
elif choice == "Dashboard":
    if not st.session_state.get('user_id'):
        st.warning("Please login to access your dashboard.")
    else:
        user = current_user(db)
        st.header("Dashboard")

        if user.user_type == 'patient':
            # fetch patient profile
            patient = db.query(Patient).filter(Patient.user_id == user.id).first()
            if not patient:
                st.info("Patient profile not found.")
            else:
                st.subheader(f"Welcome, {patient.first_name} {patient.last_name}")
                st.write(f"Date of birth: {patient.date_of_birth.isoformat()}")
                st.write(f"Gender: {patient.gender}")
                st.write(f"Phone: {user.phone}")
                if patient.address:
                    st.write(f"Address: {patient.address}")

                st.markdown("---")
                st.subheader("Your Lab Results")
                results = db.query(LabResult).filter(LabResult.patient_id == patient.id).order_by(LabResult.test_date.desc()).all()
                if not results:
                    st.info("You don't have any lab results yet.")
                else:
                    for res in results:
                        with st.expander(f"{res.test_type} — {res.test_date.date()} — {res.status}"):
                            st.write(f"Result date: {res.result_date.date()}")
                            st.write(f"Status: {res.status}")
                            if res.lab_technician:
                                st.write(f"Lab technician: {res.lab_technician}")
                            if res.notes:
                                st.write("Notes:")
                                st.write(res.notes)
                            if res.file_path:
                                filepath = os.path.join(UPLOAD_FOLDER, res.file_path)
                                try:
                                    with open(filepath, "rb") as f:
                                        data = f.read()
                                    st.download_button(
                                        label="Download result file",
                                        data=data,
                                        file_name=res.file_path,
                                        mime="application/octet-stream"
                                    )
                                except FileNotFoundError:
                                    st.warning("File not found on server.")

        elif user.user_type == 'doctor':
            st.subheader(f"Welcome, Dr. {user.doctor_profile.last_name if user.doctor_profile else user.username}")
            st.markdown("---")
            st.subheader("All Lab Results")
            results = db.query(LabResult).order_by(LabResult.test_date.desc()).all()
            if not results:
                st.info("No lab results available.")
            else:
                for res in results:
                    patient = db.query(Patient).get(res.patient_id)
                    label = f"{patient.first_name} {patient.last_name} — {res.test_type} — {res.test_date.date()}"
                    with st.expander(label):
                        st.write(f"Patient: {patient.first_name} {patient.last_name}")
                        st.write(f"Test type: {res.test_type}")
                        st.write(f"Test date: {res.test_date.date()}")
                        st.write(f"Result date: {res.result_date.date()}")
                        st.write(f"Status: {res.status}")
                        if res.notes:
                            st.write("Notes:")
                            st.write(res.notes)
                        if res.file_path:
                            path = os.path.join(UPLOAD_FOLDER, res.file_path)
                            try:
                                with open(path, "rb") as f:
                                    data = f.read()
                                st.download_button(
                                    label="Download file",
                                    data=data,
                                    file_name=res.file_path,
                                    mime="application/octet-stream"
                                )
                            except FileNotFoundError:
                                st.warning("File not found on server.")

        elif user.user_type == 'lab_tech':
            st.subheader(f"Welcome, {user.username} (Lab Technician)")
            st.markdown("---")
            st.subheader("Pending Results (status = pending)")
            pending = db.query(LabResult).filter(LabResult.status == 'pending').all()
            if not pending:
                st.info("No pending results.")
            else:
                for res in pending:
                    patient = db.query(Patient).get(res.patient_id)
                    st.write(f"{patient.first_name} {patient.last_name} — {res.test_type} — {res.test_date.date()}")

            st.markdown("---")
            st.subheader("Completed Results")
            completed = db.query(LabResult).filter(LabResult.status == 'completed').order_by(LabResult.test_date.desc()).all()
            if not completed:
                st.info("No completed results yet.")
            else:
                for res in completed:
                    patient = db.query(Patient).get(res.patient_id)
                    with st.expander(f"{patient.first_name} {patient.last_name} — {res.test_type} — {res.test_date.date()}"):
                        st.write(f"Result date: {res.result_date.date()}")
                        if res.file_path:
                            path = os.path.join(UPLOAD_FOLDER, res.file_path)
                            try:
                                with open(path, "rb") as f:
                                    data = f.read()
                                st.download_button(
                                    label="Download file",
                                    data=data,
                                    file_name=res.file_path,
                                    mime="application/octet-stream"
                                )
                            except FileNotFoundError:
                                st.warning("File not found on server.")
                        if res.notes:
                            st.write("Notes:")
                            st.write(res.notes)

# Close DB session at the end of request (good practice)
# Note: SessionLocal is scoped_session; explicit remove can be used when app exits.
# We won't call remove here to avoid interfering with Streamlit re-runs.
