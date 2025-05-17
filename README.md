# 🗓️ Teacher Timetable Generator using OR-Tools

This project generates an optimized weekly timetable for teachers based on lecture, tutorial, and practical hour requirements using Google OR-Tools' CP-SAT solver. It enforces constraints like maximum daily teaching load, practical continuity, and slot-type assignment (Morning, Afternoon, Evening).

## 📦 Features

- 📊 Input from a structured CSV file containing subjects and faculty assignments
- ⏰ Considers lecture, tutorial, and lab (practical) hours separately
- 📅 Weekly schedule for 6 days (Monday to Saturday)
- 🔁 Enforces **consecutive lab slot** allocation
- ⛔ Avoids over-allocating teachers (e.g., max 5 hours/day)
- 🧠 Smart slot assignment using predefined slot types (A, B, C)
- ✅ Validates and filters input for completeness and correctness

---

## 🧾 Input CSV Format

The CSV must include the following columns:

| course_code | Faculty    | lecture_hours | tutorial_hours | practical_hours | credits |
|-------------|------------|----------------|-----------------|------------------|---------|
| CSE101      | Dr. Smith  | 3              | 1               | 2                | 4       |
| CSE102      | Dr. Jane   | 2              | 0               | 2                | 3       |

Ensure the `credits` are between 1 and 5. Teachers with invalid or missing data will be skipped.

---

## 🛠️ How It Works

1. **Reads** input CSV file using pandas
2. **Processes** subject-teacher relationships and slot needs
3. **Creates** decision variables for each type of session
4. **Applies constraints**:
   - Max hours/day: `5`
   - Max consecutive theory slots: `2`
   - Practical sessions must be scheduled in **consecutive** lab slots
   - Slot-type logic (A: Morning, B: Afternoon, C: Evening)
5. **Solves** the constraint satisfaction problem using OR-Tools CP-SAT

---

## 🚀 Getting Started

### 🔧 Requirements

- Python 3.8+
- `pandas`
- `ortools`

### 💻 Installation

```bash
pip install pandas ortools
