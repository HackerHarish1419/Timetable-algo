
# 🧠 CP-SAT Based Timetable Scheduler using OR-Tools

A powerful, constraint-programming-based scheduler for academic timetabling using Google's OR-Tools (CP-SAT Solver). It supports practical, tutorial, and lecture slot allocation with advanced constraints like teacher load limits, consecutive lab sessions, and slot-type logic.

---

## 📌 Features

- ✅ Automatic allocation of **lecture, tutorial, and practical hours** per subject.
- ✅ Assignment of **teachers to slots** with maximum daily/hourly constraints.
- ✅ **Practical lab constraints**: Assigned in consecutive pairs (e.g., L1+L2).
- ✅ **Slot type system** (A, B, C): Teachers can switch types across days with conditions.
- ✅ Handles **571 teachers**, **1155 subjects**, and **multiple departments**.
- ✅ Generates a **conflict-free schedule** in CSV format.

---

## ⚙️ Setup Instructions

1. **Clone this repository**:
   ```bash
   git clone https://github.com/your-repo/timetable-cpsat.git
   cd timetable-cpsat
   ```

2. **Install dependencies**:
   ```bash
   pip install ortools pandas
   ```

3. **Prepare your input files** (see below for format):
   - `teachers.csv`
   - `courses.csv`
   - `rooms.csv`

4. **Run the solver**:
   ```bash
   python main.py
   ```

---

## 🗂️ Input Data Format

### `teachers.csv`
| teacher_id | name         |
|------------|--------------|
| T001       | John Doe     |

### `courses.csv`
| course_code | subject_name | teacher_id | type     | hours_per_week |
|-------------|--------------|------------|----------|----------------|
| CS101       | DSA          | T001       | Lecture  | 3              |
| CS101       | DSA Lab      | T002       | Practical| 2              |

### `rooms.csv`
| room_id | type      | capacity |
|---------|-----------|----------|
| R101    | theory    | 60       |
| L201    | practical | 30       |

---

## ⏰ Slot System

### Theory Slots:
- `L1`, `L2`, ..., `L6` (per day)

### Lab Slots (for practicals):
- `L1`, `L2` (must be paired)
- `L3`, `L4`
- `L5`, `L6`

### Slot Types:
| Type | Start-End Time | Labels             |
|------|----------------|--------------------|
| A    | 8am–3pm        | L1–L4              |
| B    | 10am–5pm       | L2–L5              |
| C    | 12pm–7pm       | L3–L6              |

---

## 🧾 Constraints Implemented

### ✅ 1. Subject Hours (Hard Constraint)
Each subject must be scheduled exactly for its required hours (Lecture, Tutorial, Practical).

### ✅ 2. Practical Consecutive Slots
Practicals must be assigned in consecutive lab slot pairs like (L1, L2).

### ✅ 3. No Double Booking
A teacher cannot be assigned to two different subjects in the same time slot.

### ✅ 4. Max Hours per Day
Each teacher can have at most `MAX_HOURS_PER_DAY` slots (default = 5) in a single day.

### ✅ 5. Max Consecutive Slots
Each teacher may not teach more than `MAX_CONSECUTIVE_SLOTS` (e.g., 3) without a break.

### ✅ 6. Slot Type (A, B, C)
Each teacher per day gets assigned to **one slot type**. If a teacher teaches in slot type C on a day, they can only teach in type B or C the next day.

### ✅ 7. Lab Capacity & Batching
Practical sessions are split into batches. One teacher per batch. If 2 hours practical → 2 batches with different teachers.

### ✅ 8. Theory and Lab Non-Overlap
Theory and lab sessions cannot be assigned in overlapping slots for a teacher.

---

## 📤 Output Format

Generates `timetable_output.csv` with the following columns:

| Day   | Slot | Teacher | Subject     | Type     | Room  |
|-------|------|---------|-------------|----------|-------|
| Mon   | L1   | T001    | DSA         | Lecture  | R101  |
| Tue   | L3-L4| T002    | DSA Lab     | Practical| L201  |

---

## 📈 Scalability

- Handles **hundreds of teachers** and **thousands of subjects**.
- Easily configurable to add departments, batch handling, elective grouping, and more.

---

## 🧠 Future Enhancements

- GUI for visual timetable editing.
- Preference-based teacher allocation.
- Student timetable generation from master schedule.
- Room conflict checks and auto-allocation.

---

## 👨‍💻 Developed With

- Python
- [Google OR-Tools](https://developers.google.com/optimization)
- Pandas

---
