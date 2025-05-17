import pandas as pd
from ortools.sat.python import cp_model
import logging

# Constants
HOURS_PER_CREDIT = 18
WEEKS_IN_SEMESTER = 18
MAX_HOURS_PER_DAY = 5
MORNING_SLOTS = [0, 1, 2]  # Slots representing morning hours
SURVEY_LAB_CODE = 'CE23331'  # Survey Lab course code

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def create_timetable(csv_file_path):
    try:
        # Read the CSV file
        df = pd.read_csv(csv_file_path)
    except FileNotFoundError:
        logging.error(f"File not found: {csv_file_path}")
        return None
    except pd.errors.EmptyDataError:
        logging.error(f"File is empty or invalid: {csv_file_path}")
        return None

    # Validate required columns
    required_columns = ['Credits', 'Code', 'Faculty']
    if not all(col in df.columns for col in required_columns):
        logging.error(f"Missing required columns in the CSV file. Required: {required_columns}")
        return None

    # Filter and clean data
    df['Credits'] = pd.to_numeric(df['Credits'], errors='coerce')
    df = df.dropna(subset=['Credits'])
    df = df[(df['Credits'] >= 1) & (df['Credits'] <= 5)]

    if df.empty:
        logging.error("No valid data found after filtering.")
        return None

    df['Subject'] = df['Code']

    # Prepare data for scheduling
    teachers = sorted(df['Faculty'].dropna().unique().tolist())
    subject_credits = dict(zip(df['Subject'], df['Credits']))
    teacher_subjects = {teacher: df[df['Faculty'] == teacher]['Subject'].unique().tolist()
                        for teacher in teachers}

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']  # Changed to include Saturday
    num_slots = 7
    all_slots = [(d, s) for d in range(len(days)) for s in range(num_slots)]

    # Calculate weekly slots per subject
    subject_weekly_slots = {}
    for subj, credits in subject_credits.items():
        total_hours = credits * HOURS_PER_CREDIT
        weekly_hours = total_hours / WEEKS_IN_SEMESTER
        subject_weekly_slots[subj] = max(1, round(weekly_hours))

    slot_categories = {
        0: 0, 1: 0, 2: 0,  # Morning
        3: 1, 4: 1,        # Afternoon
        5: 2, 6: 2         # Evening
    }

    # Get survey lab codes
    survey_lab_codes = df[df['Code'] == SURVEY_LAB_CODE]['Code'].unique().tolist()

    # Create the CP-SAT model
    model = cp_model.CpModel()

    # Define variables
    subject_assignments = {}
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            for d in range(len(days)):
                for s in range(num_slots):
                    subject_assignments[(teacher, subj, d, s)] = model.NewBoolVar(
                        f'{teacher}_{subj}_day{d}_slot{s}')

    teacher_day_category = {}
    for teacher in teachers:
        for d in range(len(days)):
            teacher_day_category[(teacher, d)] = model.NewIntVar(0, 2, f'{teacher}_day{d}_category')

    # Add constraints
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            weekly_slots = subject_weekly_slots[subj]
            model.Add(sum(subject_assignments[(teacher, subj, d, s)]
                          for d in range(len(days)) for s in range(num_slots)) == weekly_slots)

    for teacher in teachers:
        for d in range(len(days)):
            for s in range(num_slots):
                model.Add(sum(subject_assignments[(teacher, subj, d, s)]
                              for subj in teacher_subjects[teacher]) <= 1)

    for teacher in teachers:
        for d in range(len(days)):
            is_cat = {}
            for cat in range(3):  # Morning, Afternoon, Evening
                cat_slots = [s for s in range(num_slots) if slot_categories[s] == cat]
                is_cat[cat] = model.NewBoolVar(f'{teacher}_day{d}_uses_cat{cat}')

                category_usage = []
                for s in cat_slots:
                    for subj in teacher_subjects[teacher]:
                        category_usage.append(subject_assignments[(teacher, subj, d, s)])

                if category_usage:
                    model.AddMaxEquality(is_cat[cat], category_usage)
                else:
                    model.Add(is_cat[cat] == 0)

            model.Add(teacher_day_category[(teacher, d)] == 2).OnlyEnforceIf(is_cat[2])
            model.Add(teacher_day_category[(teacher, d)] == 1).OnlyEnforceIf(is_cat[1], is_cat[2].Not())
            model.Add(teacher_day_category[(teacher, d)] == 0).OnlyEnforceIf(is_cat[0], is_cat[1].Not(), is_cat[2].Not())

    for teacher in teachers:
        for d in range(len(days) - 1):
            c_today = model.NewBoolVar(f'{teacher}_day{d}_is_C')
            model.Add(teacher_day_category[(teacher, d)] == 2).OnlyEnforceIf(c_today)
            model.Add(teacher_day_category[(teacher, d)] != 2).OnlyEnforceIf(c_today.Not())
            model.Add(teacher_day_category[(teacher, d)] != 0).OnlyEnforceIf(c_today)

    # NEW CONSTRAINT: No slot type more than 2 or less than 1 for a teacher
    for teacher in teachers:
        # Count occurrences of each slot type (A, B, C) throughout the week
        for slot_type in range(3):  # 0=A, 1=C, 2=B (based on your mapping)
            slot_type_occurrences = []
            for d in range(len(days)):
                # Create a boolean variable for whether this day uses this slot type
                uses_slot_type = model.NewBoolVar(f'{teacher}_day{d}_uses_type{slot_type}')
                model.Add(teacher_day_category[(teacher, d)] == slot_type).OnlyEnforceIf(uses_slot_type)
                model.Add(teacher_day_category[(teacher, d)] != slot_type).OnlyEnforceIf(uses_slot_type.Not())
                slot_type_occurrences.append(uses_slot_type)
            
            # Add constraint: at least 1 but not more than 2 of each slot type
            model.Add(sum(slot_type_occurrences) >= 1)
            model.Add(sum(slot_type_occurrences) <= 2)

    # 1. Open Elective constraint - same time slot across years
    def add_open_elective_constraints(model, subject_assignments, teachers, days, num_slots):
        open_elective_slots = {}
        for d in range(len(days)):
            for s in range(num_slots):
                open_elective_slots[(d, s)] = model.NewBoolVar(f'open_elective_slot_day{d}_slot{s}')
                
                # Collect all open elective assignments for this slot
                slot_assignments = []
                for teacher in teachers:
                    for subj in teacher_subjects[teacher]:
                        if 'OpenElective' in subj:  # Assuming open elective courses have 'OpenElective' in their name
                            slot_assignments.append(subject_assignments[(teacher, subj, d, s)])
                
                # If any open elective is scheduled in this slot, all other open electives must be in the same slot
                if slot_assignments:
                    model.Add(sum(slot_assignments) > 0).OnlyEnforceIf(open_elective_slots[(d, s)])
                    model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(open_elective_slots[(d, s)].Not())

    # 2. Maximum 5 working hours per faculty per day
    for teacher in teachers:
        for d in range(len(days)):
            day_slots = []
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    day_slots.append(subject_assignments[(teacher, subj, d, s)])
            model.Add(sum(day_slots) <= MAX_HOURS_PER_DAY)

    # 3. Survey Lab constraint - morning slots only
    for teacher in teachers:
        for d in range(len(days)):
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    if subj in survey_lab_codes:  # Check if subject is a survey lab course
                        if s not in MORNING_SLOTS:
                            model.Add(subject_assignments[(teacher, subj, d, s)] == 0)

    # 4. Monday or Saturday off constraint
    for teacher in teachers:
        # Create boolean variables for Monday and Saturday working status
        works_monday = model.NewBoolVar(f'{teacher}_works_monday')
        works_saturday = model.NewBoolVar(f'{teacher}_works_saturday')

        # Calculate if teacher works on Monday (day 0)
        monday_slots = []
        for s in range(num_slots):
            for subj in teacher_subjects[teacher]:
                monday_slots.append(subject_assignments[(teacher, subj, 0, s)])
        model.Add(sum(monday_slots) > 0).OnlyEnforceIf(works_monday)
        model.Add(sum(monday_slots) == 0).OnlyEnforceIf(works_monday.Not())

        # Calculate if teacher works on Saturday (day 5)
        saturday_slots = []
        for s in range(num_slots):
            for subj in teacher_subjects[teacher]:
                saturday_slots.append(subject_assignments[(teacher, subj, 5, s)])
        model.Add(sum(saturday_slots) > 0).OnlyEnforceIf(works_saturday)
        model.Add(sum(saturday_slots) == 0).OnlyEnforceIf(works_saturday.Not())

        # Ensure either Monday or Saturday is a holiday (not both can be working days)
        model.Add(works_monday + works_saturday <= 1)

    # Call the open elective constraint function
    add_open_elective_constraints(model, subject_assignments, teachers, days, num_slots)

    # Solve the model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    # Generate timetables
    timetables = {}
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        for teacher in teachers:
            timetable = []
            for d in range(len(days)):
                row = [teacher, days[d]]
                
                # Check if it's Monday (d=0) or Saturday (d=5)
                is_off_day = False
                if d == 0:  # Monday
                    is_off_day = solver.Value(works_monday) == 0
                elif d == 5:  # Saturday
                    is_off_day = solver.Value(works_saturday) == 0
                
                # If it's an off day, fill all slots with "OFF"
                if is_off_day:
                    row.extend(["OFF"] * num_slots)
                    row.append("OFF DAY")
                else:
                    # Regular day - fill with scheduled classes
                    for s in range(num_slots):
                        cell_value = ""
                        for subj in teacher_subjects[teacher]:
                            if solver.Value(subject_assignments[(teacher, subj, d, s)]):
                                cell_value = subj
                                break
                        row.append(cell_value)
                    
                    day_cat = solver.Value(teacher_day_category[(teacher, d)])
                    category_names = {0: "A (8–3)", 2: "B (10–5)", 1: "C (12–7)"}
                    row.append(category_names[day_cat])
                
                timetable.append(row)
                
            columns = ["Teacher", "Day"] + [f"Slot {s+1}" for s in range(num_slots)] + ["SlotType"]
            timetables[teacher] = pd.DataFrame(timetable, columns=columns)

        logging.info("✅ Timetable successfully created")
        return timetables
    else:
        logging.error(f"❌ No feasible schedule found. Solver status: {solver.StatusName(status)}")
        return None


def export_timetable_to_csv(timetables, output_file="teacher_timetables.csv"):
    if timetables is None:
        logging.warning("No timetable data to export.")
        return None

    all_timetables = pd.concat(timetables.values(), ignore_index=True)

    # Export to CSV
    all_timetables.to_csv(output_file, index=False)
    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file


def export_timetable_to_excel(timetables, output_file="teacher_timetables.xlsx"):
    if timetables is None:
        logging.warning("No timetable data to export.")
        return None

    all_timetables = pd.concat(timetables.values(), ignore_index=True)

    # Export to Excel
    with pd.ExcelWriter(output_file) as writer:
        all_timetables.to_excel(writer, sheet_name="All Teachers", index=False)

        for teacher, df in timetables.items():
            sheet_name = teacher[:31]  # Excel has a 31-character sheet name limit
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file