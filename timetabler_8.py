import pandas as pd
from ortools.sat.python import cp_model
import logging

MAX_HOURS_PER_DAY = 5
MAX_CONSECUTIVE_SLOTS = 2  # max consecutive teaching slots
MORNING_SLOTS = [0, 1, 2]
SURVEY_LAB_CODE = 'CE23331'

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def create_timetable(csv_file_path):
    try:
        df = pd.read_csv(csv_file_path)
    except FileNotFoundError:
        logging.error(f"File not found: {csv_file_path}")
        return None
    except pd.errors.EmptyDataError:
        logging.error(f"File is empty or invalid: {csv_file_path}")
        return None

    required_columns = ['course_code', 'Faculty', 'lecture_hours', 'tutorial_hours', 'practical_hours', 'credits']
    if not all(col in df.columns for col in required_columns):
        logging.error(f"Missing required columns in CSV. Required: {required_columns}")
        return None

    # Convert numeric columns
    for col in ['lecture_hours', 'tutorial_hours', 'practical_hours', 'credits']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['credits'])
    df = df[(df['credits'] >= 1) & (df['credits'] <= 5)]

    if df.empty:
        logging.error("No valid data found after filtering.")
        return None

    df['Subject'] = df['course_code']

    teachers = sorted(df['Faculty'].dropna().unique().tolist())

    subject_lecture_hours = dict(zip(df['Subject'], df['lecture_hours']))
    subject_tutorial_hours = dict(zip(df['Subject'], df['tutorial_hours']))
    subject_practical_hours = dict(zip(df['Subject'], df['practical_hours']))
    subject_credits = dict(zip(df['Subject'], df['credits']))

    teacher_subjects = {teacher: df[df['Faculty'] == teacher]['Subject'].unique().tolist() for teacher in teachers}

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    num_slots = 7

    # Calculate weekly slots and mark subjects needing consecutive slots (practicals)
    subject_weekly_slots = {}
    subject_consecutive_slots = {}
    for subj in df['Subject'].unique():
        subj_data = df[df['Subject'] == subj].iloc[0]
        lecture_slots = subj_data['lecture_hours']
        tutorial_slots = subj_data['tutorial_hours']
        practical_slots = subj_data['practical_hours'] * 2  # practicals need double slots (consecutive)
        total_slots = lecture_slots + tutorial_slots + practical_slots
        subject_weekly_slots[subj] = int(total_slots)
        subject_consecutive_slots[subj] = practical_slots > 0

    # Slot categories: 0=Morning,1=Afternoon,2=Evening
    slot_categories = {
        0: 0, 1: 0, 2: 0,  # Morning
        3: 1, 4: 1,        # Afternoon
        5: 2, 6: 2         # Evening
    }

    model = cp_model.CpModel()

    # Variables
    subject_assignments = {}
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            for d in range(len(days)):
                for s in range(num_slots):
                    subject_assignments[(teacher, subj, d, s)] = model.NewBoolVar(f'{teacher}_{subj}_day{d}_slot{s}')

    practical_sessions = {}
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            if subject_consecutive_slots.get(subj, False):
                for d in range(len(days)):
                    for s in range(num_slots - 1):
                        practical_sessions[(teacher, subj, d, s)] = model.NewBoolVar(f'{teacher}_{subj}_practical_day{d}_slot{s}')

    # Teacher teaching any subject at slot
    teacher_teaching = {}
    for teacher in teachers:
        for d in range(len(days)):
            for s in range(num_slots):
                teacher_teaching[(teacher, d, s)] = model.NewBoolVar(f'{teacher}_teaching_day{d}_slot{s}')
                subj_vars = [subject_assignments[(teacher, subj, d, s)] for subj in teacher_subjects[teacher]]
                if subj_vars:
                    model.AddMaxEquality(teacher_teaching[(teacher, d, s)], subj_vars)
                else:
                    model.Add(teacher_teaching[(teacher, d, s)] == 0)

    # Constraints

    # Each subject assigned required weekly slots per teacher
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            model.Add(
                sum(subject_assignments[(teacher, subj, d, s)] for d in range(len(days)) for s in range(num_slots))
                == subject_weekly_slots[subj]
            )

    # Practical sessions: ensure consecutive slots
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            if subject_consecutive_slots.get(subj, False):
                practical_hours = subject_practical_hours.get(subj, 0)
                if practical_hours > 0:
                    # If practical session starts at (d,s), next slot also assigned to same subj
                    for d in range(len(days)):
                        for s in range(num_slots - 1):
                            model.Add(subject_assignments[(teacher, subj, d, s)] == 1).OnlyEnforceIf(practical_sessions[(teacher, subj, d, s)])
                            model.Add(subject_assignments[(teacher, subj, d, s + 1)] == 1).OnlyEnforceIf(practical_sessions[(teacher, subj, d, s)])
                    # Number of practical sessions = practical_hours / 2
                    model.Add(
                        sum(practical_sessions[(teacher, subj, d, s)] for d in range(len(days)) for s in range(num_slots - 1))
                        == practical_hours // 2
                    )

    # A teacher can only teach one subject per slot
    for teacher in teachers:
        for d in range(len(days)):
            for s in range(num_slots):
                model.Add(
                    sum(subject_assignments[(teacher, subj, d, s)] for subj in teacher_subjects[teacher]) <= 1
                )

    # No more than MAX_CONSECUTIVE_SLOTS consecutive teaching slots
    for teacher in teachers:
        for d in range(len(days)):
            for s_start in range(num_slots - MAX_CONSECUTIVE_SLOTS):
                consecutive_vars = [teacher_teaching[(teacher, d, s)] for s in range(s_start, s_start + MAX_CONSECUTIVE_SLOTS + 1)]
                model.Add(sum(consecutive_vars) <= MAX_CONSECUTIVE_SLOTS)

    # Teacher day category: 0=Morning,1=Afternoon,2=Evening
    teacher_day_category = {}
    for teacher in teachers:
        for d in range(len(days)):
            teacher_day_category[(teacher, d)] = model.NewIntVar(0, 2, f'{teacher}_day{d}_category')

    for teacher in teachers:
        for d in range(len(days)):
            # Boolean variables if teacher uses a category that day
            is_cat = {}
            for cat in range(3):
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

            # Assign day category according to priority Evening(2) > Afternoon(1) > Morning(0)
            # Implement precedence with intermediate bools:
            model.AddImplication(is_cat[2], teacher_day_category[(teacher, d)] == 2)
            model.AddImplication(is_cat[1], teacher_day_category[(teacher, d)] == 1).Only
            # model.Add(sum(slot_assignments) > 0).OnlyEnforceIf(open_elective_slots[(d, s)])
            # model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(open_elective_slots[(d, s)].Not())
                # (Removed incomplete or misplaced open elective constraints)

    # (Removed call to add_open_elective_constraints as it is undefined and not implemented)

    # Objective: Minimize total teaching hours per teacher per day (optional, can be customized)
    # For example, minimize number of teaching slots assigned overall
    model.Minimize(
        sum(teacher_teaching[(teacher, d, s)] for teacher in teachers for d in range(len(days)) for s in range(num_slots))
    )

    # Solve model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        timetable = []
        for teacher in teachers:
            for d in range(len(days)):
                for s in range(num_slots):
                    for subj in teacher_subjects[teacher]:
                        if solver.Value(subject_assignments[(teacher, subj, d, s)]) == 1:
                            timetable.append({
                                'Teacher': teacher,
                                'Day': days[d],
                                'Slot': s,
                                'Subject': subj
                            })
        timetable_df = pd.DataFrame(timetable)
        return timetable_df
    else:
        logging.warning("No feasible solution found.")
        return None


if __name__ == "__main__":
    csv_path = "courses.csv"
    timetable_df = create_timetable(csv_path)
    if timetable_df is not None:
        print(timetable_df)
    else:
        print("Failed to create timetable.")
