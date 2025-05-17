import pandas as pd
from ortools.sat.python import cp_model
import logging

MAX_HOURS_PER_DAY = 5
MAX_CONSECUTIVE_SLOTS = 2  # New constraint: maximum consecutive teaching slots
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
        logging.error(f"Missing required columns in the CSV file. Required: {required_columns}")
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
    
    # Identify practical courses with 60 students for splitting
    practical_courses_with_60_students = []
    for course_code in df['course_code'].unique():
        course_data = df[df['course_code'] == course_code]
        if course_data['practical_hours'].iloc[0] > 0 and course_data['registration'].iloc[0] == 60:
            practical_courses_with_60_students.append(course_code)

    # Create qualified teachers dictionary
    qualified_teachers = {}
    for course in practical_courses_with_60_students:
        qualified_teachers[course] = df[df['course_code'] == course]['Faculty'].unique().tolist()

    # Create dictionaries for hours
    subject_lecture_hours = dict(zip(df['Subject'], df['lecture_hours']))
    subject_tutorial_hours = dict(zip(df['Subject'], df['tutorial_hours']))
    subject_practical_hours = dict(zip(df['Subject'], df['practical_hours']))
    subject_credits = dict(zip(df['Subject'], df['credits']))
    
    teacher_subjects = {teacher: df[df['Faculty'] == teacher]['Subject'].unique().tolist()
                        for teacher in teachers}

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] 
    num_slots = 7
    all_slots = [(d, s) for d in range(len(days)) for s in range(num_slots)]

    # Calculate weekly slots needed for each subject, doubling practicals for split courses
    subject_weekly_slots = {}
    subject_consecutive_slots = {}  # To track which subjects need consecutive slots

    for subj in df['Subject'].unique():
        subj_data = df[df['Subject'] == subj].iloc[0]
        lecture_slots = subj_data['lecture_hours']
        tutorial_slots = subj_data['tutorial_hours']
        practical_slots = subj_data['practical_hours']
        
        # Double practical slots for split courses
        if subj in practical_courses_with_60_students:
            practical_slots *= 2
        
        total_slots = lecture_slots + tutorial_slots + practical_slots
        subject_weekly_slots[subj] = int(total_slots)
        
        # Mark if this subject has practicals (needs consecutive slots)
        subject_consecutive_slots[subj] = practical_slots > 0

    slot_categories = {
        0: 0, 1: 0, 2: 0,  # Morning
        3: 1, 4: 1,        # Afternoon
        5: 2, 6: 2         # Evening
    }

    survey_lab_codes = df[df['course_code'] == SURVEY_LAB_CODE]['course_code'].unique().tolist()

    model = cp_model.CpModel()

    # Define variables
    subject_assignments = {}
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            for d in range(len(days)):
                for s in range(num_slots):
                    subject_assignments[(teacher, subj, d, s)] = model.NewBoolVar(
                        f'{teacher}_{subj}_day{d}_slot{s}')

    # For practical sessions (need consecutive slots) for non-split courses
    practical_sessions = {}
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            if subject_consecutive_slots.get(subj, False) and subj not in practical_courses_with_60_students:
                for d in range(len(days)):
                    for s in range(num_slots-1):
                        practical_sessions[(teacher, subj, d, s)] = model.NewBoolVar(
                            f'{teacher}_{subj}_practical_day{d}_slot{s}')

    # Teacher teaching in a slot (any subject)
    teacher_teaching = {}
    for teacher in teachers:
        for d in range(len(days)):
            for s in range(num_slots):
                teacher_teaching[(teacher, d, s)] = model.NewBoolVar(f'{teacher}_teaching_day{d}_slot{s}')
                
                # Link to subject assignments
                subject_taught = []
                for subj in teacher_subjects[teacher]:
                    subject_taught.append(subject_assignments[(teacher, subj, d, s)])
                
                if subject_taught:
                    model.Add(sum(subject_taught) >= 1).OnlyEnforceIf(teacher_teaching[(teacher, d, s)])
                    model.Add(sum(subject_taught) == 0).OnlyEnforceIf(teacher_teaching[(teacher, d, s)].Not())
                else:
                    model.Add(teacher_teaching[(teacher, d, s)] == 0)

    # Teacher day category
    teacher_day_category = {}
    for teacher in teachers:
        for d in range(len(days)):
            teacher_day_category[(teacher, d)] = model.NewIntVar(0, 2, f'{teacher}_day{d}_category')

    # Handle batch splitting for practical courses with 60 students
    for course in practical_courses_with_60_students:
        if len(qualified_teachers[course]) >= 2:
            # Create variables for each possible batch assignment (teacher, day, slot)
            batch1_assignments = {}
            batch2_assignments = {}
            for teacher in qualified_teachers[course]:
                for d in range(len(days)):
                    for s in range(num_slots):
                        batch1_assignments[(teacher, d, s)] = model.NewBoolVar(
                            f'batch1_{course}_{teacher}_day{d}_slot{s}')
                        batch2_assignments[(teacher, d, s)] = model.NewBoolVar(
                            f'batch2_{course}_{teacher}_day{d}_slot{s}')
            
            # Ensure each batch is assigned exactly once
            model.Add(sum(batch1_assignments.values()) == 1)
            model.Add(sum(batch2_assignments.values()) == 1)
            
            # Connect batch assignments to the main assigned variables
            for teacher in qualified_teachers[course]:
                for d in range(len(days)):
                    for s in range(num_slots):
                        model.Add(subject_assignments[(teacher, course, d, s)] == 1).OnlyEnforceIf(
                            batch1_assignments[(teacher, d, s)])
                        model.Add(subject_assignments[(teacher, course, d, s)] == 1).OnlyEnforceIf(
                            batch2_assignments[(teacher, d, s)])
            
            # Constraint: Different teachers for each batch
            for teacher in qualified_teachers[course]:
                for d1 in range(len(days)):
                    for s1 in range(num_slots):
                        for d2 in range(len(days)):
                            for s2 in range(num_slots):
                                model.Add(batch1_assignments[(teacher, d1, s1)] + 
                                          batch2_assignments[(teacher, d2, s2)] <= 1)
            
            # Constraint: Different time slots for each batch
            for d in range(len(days)):
                for s in range(num_slots):
                    batch1_in_slot = []
                    batch2_in_slot = []
                    for teacher in qualified_teachers[course]:
                        batch1_in_slot.append(batch1_assignments[(teacher, d, s)])
                        batch2_in_slot.append(batch2_assignments[(teacher, d, s)])
                    model.Add(sum(batch1_in_slot + batch2_in_slot) <= 1)
            
            # Handle consecutive slots for each batch if applicable
            practical_hours = int(df[df['course_code'] == course]['practical_hours'].iloc[0])
            if practical_hours >= 2:
                consecutive_slots = 2  # Assuming 2-hour practical sessions
                batch1_starts = {}
                batch2_starts = {}
                for teacher in qualified_teachers[course]:
                    for d in range(len(days)):
                        for s in range(num_slots - consecutive_slots + 1):
                            batch1_starts[(teacher, d, s)] = model.NewBoolVar(
                                f'batch1_{course}_{teacher}_start_day{d}_slot{s}')
                            batch2_starts[(teacher, d, s)] = model.NewBoolVar(
                                f'batch2_{course}_{teacher}_start_day{d}_slot{s}')
                
                # Connect start variables to assignment variables
                for teacher in qualified_teachers[course]:
                    for d in range(len(days)):
                        for s in range(num_slots - consecutive_slots + 1):
                            for i in range(consecutive_slots):
                                model.Add(subject_assignments[(teacher, course, d, s+i)] == 1).OnlyEnforceIf(
                                    batch1_starts[(teacher, d, s)])
                                model.Add(subject_assignments[(teacher, course, d, s+i)] == 1).OnlyEnforceIf(
                                    batch2_starts[(teacher, d, s)])
                
                # Ensure each batch has exactly one start position
                model.Add(sum(batch1_starts.values()) == 1)
                model.Add(sum(batch2_starts.values()) == 1)
        else:
            logging.warning(f"Course {course} does not have enough qualified teachers for two batches")

    # Ensure subjects get their required number of weekly slots
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            weekly_slots = subject_weekly_slots[subj]
            model.Add(sum(subject_assignments[(teacher, subj, d, s)]
                          for d in range(len(days)) for s in range(num_slots)) == weekly_slots)
    
    # Ensure practical sessions for non-split courses get consecutive slots
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            if subject_consecutive_slots.get(subj, False) and subj not in practical_courses_with_60_students:
                practical_hours = subject_practical_hours.get(subj, 0)
                if practical_hours > 0:
                    for d in range(len(days)):
                        for s in range(num_slots-1):
                            model.Add(subject_assignments[(teacher, subj, d, s)] == 1).OnlyEnforceIf(practical_sessions[(teacher, subj, d, s)])
                            model.Add(subject_assignments[(teacher, subj, d, s+1)] == 1).OnlyEnforceIf(practical_sessions[(teacher, subj, d, s)])
                    
                    if practical_hours >= 2:
                        model.Add(sum(practical_sessions[(teacher, subj, d, s)] 
                                    for d in range(len(days)) for s in range(num_slots-1)) == practical_hours // 2)

    # Ensure a teacher can only teach one subject per time slot
    for teacher in teachers:
        for d in range(len(days)):
            for s in range(num_slots):
                model.Add(sum(subject_assignments[(teacher, subj, d, s)]
                              for subj in teacher_subjects[teacher]) <= 1)

    # NEW CONSTRAINT: No more than MAX_CONSECUTIVE_SLOTS consecutive teaching slots
    for teacher in teachers:
        for d in range(len(days)):
            for s_start in range(num_slots - MAX_CONSECUTIVE_SLOTS):
                consecutive_vars = []
                for s in range(s_start, s_start + MAX_CONSECUTIVE_SLOTS + 1):
                    consecutive_vars.append(teacher_teaching[(teacher, d, s)])
                model.Add(sum(consecutive_vars) <= MAX_CONSECUTIVE_SLOTS)

    # Teacher day category assignments
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

    # Daily pattern constraints
    for teacher in teachers:
        for d in range(len(days) - 1):
            c_today = model.NewBoolVar(f'{teacher}_day{d}_is_C')
            model.Add(teacher_day_category[(teacher, d)] == 2).OnlyEnforceIf(c_today)
            model.Add(teacher_day_category[(teacher, d)] != 2).OnlyEnforceIf(c_today.Not())
            model.Add(teacher_day_category[(teacher, d)] != 0).OnlyEnforceIf(c_today)

    # Slot type occurrence constraints
    for teacher in teachers:
        for slot_type in range(3):
            slot_type_occurrences = []
            for d in range(len(days)):
                uses_slot_type = model.NewBoolVar(f'{teacher}_day{d}_uses_type{slot_type}')
                model.Add(teacher_day_category[(teacher, d)] == slot_type).OnlyEnforceIf(uses_slot_type)
                model.Add(teacher_day_category[(teacher, d)] != slot_type).OnlyEnforceIf(uses_slot_type.Not())
                slot_type_occurrences.append(uses_slot_type)
            
            model.Add(sum(slot_type_occurrences) >= 1)
            model.Add(sum(slot_type_occurrences) <= 2)

    # Free slot constraints based on slot type
    for teacher in teachers:
        for d in range(len(days)):
            # Type A (Morning) constraints
            a_type_constraints = model.NewBoolVar(f'{teacher}_day{d}_A_type_constraints')
            model.Add(teacher_day_category[(teacher, d)] == 0).OnlyEnforceIf(a_type_constraints)
            model.Add(teacher_day_category[(teacher, d)] != 0).OnlyEnforceIf(a_type_constraints.Not())
            
            type_a_slots = [3, 4, 5]  # Slot indices for type A
            slot_occupied = []
            for s in type_a_slots:
                is_occupied = model.NewBoolVar(f'{teacher}_day{d}_slot{s}_occupied')
                slot_assignments = []
                for subj in teacher_subjects[teacher]:
                    slot_assignments.append(subject_assignments[(teacher, subj, d, s)])
                
                if slot_assignments:
                    model.Add(sum(slot_assignments) >= 1).OnlyEnforceIf(is_occupied)
                    model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(is_occupied.Not())
                else:
                    model.Add(is_occupied == 0)
                
                slot_occupied.append(is_occupied)
            
            model.Add(sum(slot_occupied) <= len(type_a_slots) - 1).OnlyEnforceIf(a_type_constraints)
            
            # Type B (Afternoon) constraints
            b_type_constraints = model.NewBoolVar(f'{teacher}_day{d}_B_type_constraints')
            model.Add(teacher_day_category[(teacher, d)] == 2).OnlyEnforceIf(b_type_constraints)
            model.Add(teacher_day_category[(teacher, d)] != 2).OnlyEnforceIf(b_type_constraints.Not())
            
            type_b_slots = [1, 2, 3]  # Slot indices for type B
            slot_occupied = []
            for s in type_b_slots:
                is_occupied = model.NewBoolVar(f'{teacher}_day{d}_slot{s}_occupied')
                slot_assignments = []
                for subj in teacher_subjects[teacher]:
                    slot_assignments.append(subject_assignments[(teacher, subj, d, s)])
                
                if slot_assignments:
                    model.Add(sum(slot_assignments) >= 1).OnlyEnforceIf(is_occupied)
                    model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(is_occupied.Not())
                else:
                    model.Add(is_occupied == 0)
                
                slot_occupied.append(is_occupied)
            
            model.Add(sum(slot_occupied) <= len(type_b_slots) - 1).OnlyEnforceIf(b_type_constraints)
            
            # Type C (Evening) constraints
            c_type_constraints = model.NewBoolVar(f'{teacher}_day{d}_C_type_constraints')
            model.Add(teacher_day_category[(teacher, d)] == 1).OnlyEnforceIf(c_type_constraints)
            model.Add(teacher_day_category[(teacher, d)] != 1).OnlyEnforceIf(c_type_constraints.Not())
            
            type_c_slots = [0, 1]  # Slot indices for type C
            slot_occupied = []
            for s in type_c_slots:
                is_occupied = model.NewBoolVar(f'{teacher}_day{d}_slot{s}_occupied')
                slot_assignments = []
                for subj in teacher_subjects[teacher]:
                    slot_assignments.append(subject_assignments[(teacher, subj, d, s)])
                
                if slot_assignments:
                    model.Add(sum(slot_assignments) >= 1).OnlyEnforceIf(is_occupied)
                    model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(is_occupied.Not())
                else:
                    model.Add(is_occupied == 0)
                
                slot_occupied.append(is_occupied)
            
            model.Add(sum(slot_occupied) <= len(type_c_slots) - 1).OnlyEnforceIf(c_type_constraints)

    # Maximum hours per day constraint
    for teacher in teachers:
        for d in range(len(days)):
            day_slots = []
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    day_slots.append(subject_assignments[(teacher, subj, d, s)])
            model.Add(sum(day_slots) <= MAX_HOURS_PER_DAY)

    # Teacher batch assignment constraint
    for teacher in teachers:
        mon_to_fri = model.NewBoolVar(f'{teacher}_mon_to_fri')
        
        for d in range(len(days)):
            day_slots = []
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    day_slots.append(subject_assignments[(teacher, subj, d, s)])
            
            if d == 5:  # Saturday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(mon_to_fri)
            
            elif d == 0:  # Monday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(mon_to_fri.Not())

    # Open elective constraints
    def add_open_elective_constraints(model, subject_assignments, teachers, days, num_slots):
        open_elective_slots = {}
        for d in range(len(days)):
            for s in range(num_slots):
                open_elective_slots[(d, s)] = model.NewBoolVar(f'open_elective_slot_day{d}_slot{s}')
                
                slot_assignments = []
                for teacher in teachers:
                    for subj in teacher_subjects[teacher]:
                        if 'OpenElective' in subj:  
                            slot_assignments.append(subject_assignments[(teacher, subj, d, s)])
                
                if slot_assignments:
                    model.Add(sum(slot_assignments) > 0).OnlyEnforceIf(open_elective_slots[(d, s)])
                    model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(open_elective_slots[(d, s)].Not())

    add_open_elective_constraints(model, subject_assignments, teachers, days, num_slots)

    # Solve the model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    # Generate timetable
    timetables = {}
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        for teacher in teachers:
            timetable = []
            for d in range(len(days)):
                row = [teacher, days[d]]
                
                for s in range(num_slots):
                    cell_value = ""
                    for subj in teacher_subjects[teacher]:
                        if solver.Value(subject_assignments[(teacher, subj, d, s)]):
                            # Check if this is part of a practical session
                            is_practical = False
                            if subject_consecutive_slots.get(subj, False) and s > 0:
                                if solver.Value(subject_assignments[(teacher, subj, d, s-1)]):
                                    is_practical = True
                            
                            # Add a marker for practical sessions
                            if is_practical:
                                cell_value = f"{subj} (Practical)"
                            else:
                                # Check if this is the start of a practical session
                                if subject_consecutive_slots.get(subj, False) and s < num_slots-1:
                                    if solver.Value(subject_assignments[(teacher, subj, d, s+1)]):
                                        cell_value = f"{subj} (Practical)"
                                    else:
                                        cell_value = subj
                                else:
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
    
    all_timetables.to_csv(output_file, index=False)
    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file

def export_timetable_to_excel(timetables, output_file="teacher_timetables.xlsx"):
    if timetables is None:
        logging.warning("No timetable data to export.")
        return None

    all_timetables = pd.concat(timetables.values(), ignore_index=True)
    
    with pd.ExcelWriter(output_file) as writer:
        all_timetables.to_excel(writer, sheet_name="All Teachers", index=False)

        for teacher, df in timetables.items():
            sheet_name = teacher[:31]  # Excel sheet names can't exceed 31 characters
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file