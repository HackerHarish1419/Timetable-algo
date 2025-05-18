# Faculty Timetable Scheduling System
This system generates optimized teaching schedules for faculty members using constraint programming. It balances teaching loads, respects time constraints, and creates efficient timetables for academic institutions.

# Table of Contents
### Features
### Installation
### Input Format
### Slot Definitions
### Constraints
### Usage
### Output Formats
### Dependencies
### Limitations
### Troubleshooting
### Features
Automatically assigns teaching slots based on course requirements
Handles both theory classes (lectures/tutorials) and lab sessions
Enforces workload balance with time slot types (morning/afternoon/evening)
Respects faculty working day patterns (Mon-Fri or Tue-Sat)
Prevents scheduling conflicts and consecutive teaching overload
Exports timetables in multiple formats
Installation
bash
# Clone the repository
git clone https://github.com/yourusername/faculty-timetable-scheduler.git
cd faculty-timetable-scheduler

# Install dependencies
pip install pandas ortools
Input Format
The system requires a CSV file with the following columns:

# Column	Description
course_code	Unique identifier for each course
Faculty	Name of the faculty member teaching the course
lecture_hours	Number of lecture hours per week
tutorial_hours	Number of tutorial hours per week
practical_hours	Number of practical hours per week
credits	Course credit value (1-5)
Example input CSV:

## csv
course_code,Faculty,lecture_hours,tutorial_hours,practical_hours,credits
CS101,Dr. Smith,3,1,2,4
MATH201,Dr. Jones,2,2,0,3
PHYS102,Dr. Wilson,3,0,3,4
Slot Definitions
# Theory Slots
## Slot	Time
T1	8:00 - 8:50

T2	9:00 - 9:50

T3	10:00 - 10:50

T4	11:00 - 11:50

T5/T6	12:00 - 12:50

T7	1:00 - 1:50

T8	2:00 - 2:50

T9	3:00 - 3:50

T10	4:00 - 4:50

T11	5:10 - 6:00

T12	6:10 - 7:00
# Lab Slots
## Slot	Time
L1	8:00 - 8:50 / 8:50 - 9:40

L2	10:00 - 10:50 / 10:50 - 11:40

L3	11:40 - 12:30 / 12:30 - 1:20

L4	1:20 - 2:10 / 2:10 - 3:00

L5	3:00 - 3:50 / 3:50 - 4:40

L6	5:10 - 6:00 / 6:00 - 6:50
## Slot Types
Type	Description	Theory Slots	Lab Slots	Time Range

A	Morning	T1, T2, T3, T4, T5/T6, T7, T8	L1, L2, L3, L4	8:00 - 3:00

B	Afternoon	T3, T4, T5/T6, T7, T8, T9, T10	L2, L3, L4, L5	10:00 - 5:00

C	Evening	T5/T6, T7, T8, T9, T10, T11, T12	L4, L5, L6	12:00 - 7:00
## Constraints
The system enforces the following constraints:

Maximum Teaching Load:
No more than 5 teaching hours per day per faculty

Consecutive Teaching Limit:
Maximum 2 consecutive teaching slots allowed
Prevents faculty exhaustion

Slot Type Distribution:
Each faculty must have 1-2 days of each slot type (A, B, C)
Ensures fair distribution of morning, afternoon, and evening classes

Working Days Pattern:
Faculty work either Monday-Friday OR Tuesday-Saturday
Not both patterns simultaneously

Course Requirements:
All specified hours (lecture, tutorial, practical) must be scheduled
Ensures curriculum completion

Conflict Avoidance:
Faculty can only teach one subject per time slot
Prevents double-booking

Slot Type Compatibility:
Teaching assignments must respect allowed slots for each slot type

Example: A-type days can only use A-compatible slots
Usage
python
from timetable_scheduler import create_timetable, format_timetable_for_display
from timetable_scheduler import export_timetable_to_csv, export_timetable_to_excel

# Generate timetable from input data
timetables = create_timetable("faculty_courses.csv")

# Display formatted timetable in console
print(format_timetable_for_display(timetables))

# Export to different formats
export_timetable_to_csv(timetables, "faculty_schedule.csv")
export_timetable_to_excel(timetables, "faculty_schedule.xlsx")
Output Formats
Console Output
Shows a text-based representation of the timetable:

--------------------------------------------------------------------------------
THEORY TIMETABLE FOR Dr. Smith
--------------------------------------------------------------------------------
| Teacher | Day | Slot 1 | Slot 2 | Slot 3 | Slot 4 | SlotType |
|---------|-----|--------|--------|--------|--------|----------|
| Dr. Smith - Mon | Mon | CS101 (Lecture) |  | CS101 (Tutorial) |  | A (8–3) |
CSV Export
Creates a single CSV file with all faculty timetables.

# Excel Export
Creates an Excel workbook with:

Combined "All Theory" and "All Lab" sheets
Individual sheets for each faculty member
### Dependencies
pandas (>= 1.0.0): Data manipulation and analysis
ortools (>= 9.0.0): Google's operations research tools for constraint programming

logging: Standard Python logging module
## Limitations
The system assumes teaching hours are evenly distributed across the week
Lab sessions require consecutive slots (fixed requirement)
Very tight constraints might result in no feasible solution
Performance may decrease with large numbers of faculty and courses
Troubleshooting

Common Issues:
No feasible schedule found
Try relaxing some constraints (e.g., increase MAX_HOURS_PER_DAY)
Check for impossible combinations in input data
Missing data in output
Verify input CSV has all required columns
Check that data types are correct (numeric fields contain numbers)
Performance issues
For large datasets, consider splitting faculty into groups
Increase solver timeout if needed

Logging:
The system uses Python's logging module with informative messages:

✅ Success messages for successful operations
❌ Error messages when operations fail


# use the code in the file withslot.py
