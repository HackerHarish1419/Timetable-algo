import pandas as pd
from ortools.sat.python import cp_model
import logging

MAX_HOURS_PER_DAY = 5
MAX_CONSECUTIVE_SLOTS = 2  # New constraint: maximum consecutive teaching slots
MORNING_SLOTS = [0, 1, 2]    


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
    
    # Create dictionaries for hours
    # Group the data by teacher and subject to get a unique entry for each combination
    teacher_subject_data = df.groupby(['Faculty', 'Subject']).agg({
        'lecture_hours': 'first',
        'tutorial_hours': 'first',
        'practical_hours': 'first',
        'credits': 'first'
    }).reset_index()
    
    # Create dictionaries with proper teacher-subject pairs
    subject_lecture_hours = {}
    subject_tutorial_hours = {}
    subject_practical_hours = {}
    subject_credits = {}
    teacher_subjects = {teacher: [] for teacher in teachers}
    
    # Fill the dictionaries
    for _, row in teacher_subject_data.iterrows():
        teacher = row['Faculty']
        subject = row['Subject']
        key = (teacher, subject)  # Use a tuple of (teacher, subject) as the key
        
        subject_lecture_hours[key] = int(row['lecture_hours'])
        subject_tutorial_hours[key] = int(row['tutorial_hours'])
        subject_practical_hours[key] = int(row['practical_hours'])
        subject_credits[key] = int(row['credits'])
        
        # Add subject to the teacher's list
        if subject not in teacher_subjects[teacher]:
            teacher_subjects[teacher].append(subject)

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] 
    num_slots = 7
    all_slots = [(d, s) for d in range(len(days)) for s in range(num_slots)]

    # Calculate weekly slots needed for each subject based on lecture, tutorial, and practical hours
    subject_weekly_slots = {}
    subject_lecture_slots = {}    # To track lecture slots needed
    subject_tutorial_slots = {}   # To track tutorial slots needed
    subject_practical_slots = {}  # To track practical slots needed
    subject_consecutive_slots = {}  # To track which subjects need consecutive slots

    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            key = (teacher, subj)
            
            # Weekly slots for lectures (NEW: Store separately)
            lecture_slots = subject_lecture_hours[key]
            subject_lecture_slots[key] = lecture_slots
            
            # Weekly slots for tutorials (NEW: Store separately)
            tutorial_slots = subject_tutorial_hours[key]
            subject_tutorial_slots[key] = tutorial_slots
            
            # Weekly slots for practicals (NEW: Store separately)
            practical_slots = subject_practical_hours[key]
            subject_practical_slots[key] = practical_slots
            
            # Total weekly slots
            total_slots = lecture_slots + tutorial_slots + practical_slots
            
            subject_weekly_slots[key] = total_slots
            
            # Mark if this subject has practicals (needs consecutive slots)
            subject_consecutive_slots[key] = practical_slots > 0

    slot_categories = {
        0: 0, 1: 0, 2: 0,  # Morning
        3: 1, 4: 1,        # Afternoon
        5: 2, 6: 2         # Evening
    }

    model = cp_model.CpModel()

    # Define variables
    
    # Split assignment variables by type (NEW)
    lecture_assignments = {}     # For lecture hours
    tutorial_assignments = {}    # For tutorial hours 
    practical_assignments = {}   # For practical hours
    
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            key = (teacher, subj)
            
            # Only create lecture assignment variables if lecture hours > 0
            if subject_lecture_slots[key] > 0:
                for d in range(len(days)):
                    for s in range(num_slots):
                        lecture_assignments[(teacher, subj, d, s)] = model.NewBoolVar(
                            f'{teacher}_{subj}_lecture_day{d}_slot{s}')
            
            # Only create tutorial assignment variables if tutorial hours > 0
            if subject_tutorial_slots[key] > 0:
                for d in range(len(days)):
                    for s in range(num_slots):
                        tutorial_assignments[(teacher, subj, d, s)] = model.NewBoolVar(
                            f'{teacher}_{subj}_tutorial_day{d}_slot{s}')
            
            # Only create practical assignment variables if practical hours > 0
            if subject_practical_slots[key] > 0:
                for d in range(len(days)):
                    for s in range(num_slots):
                        practical_assignments[(teacher, subj, d, s)] = model.NewBoolVar(
                            f'{teacher}_{subj}_practical_day{d}_slot{s}')

    # For practical sessions (need consecutive slots)
    practical_sessions = {}
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            key = (teacher, subj)
            if subject_consecutive_slots.get(key, False):
                for d in range(len(days)):
                    # We can only start a practical session up to slot num_slots-2 to ensure there's room for 2 consecutive slots
                    for s in range(num_slots-1):
                        practical_sessions[(teacher, subj, d, s)] = model.NewBoolVar(
                            f'{teacher}_{subj}_practical_day{d}_slot{s}')

    teacher_day_category = {}
    for teacher in teachers:
        for d in range(len(days)):
            teacher_day_category[(teacher, d)] = model.NewIntVar(0, 2, f'{teacher}_day{d}_category')

    # Teacher teaching in a slot (any subject)
    teacher_teaching = {}
    for teacher in teachers:
        for d in range(len(days)):
            for s in range(num_slots):
                teacher_teaching[(teacher, d, s)] = model.NewBoolVar(f'{teacher}_teaching_day{d}_slot{s}')
                
                # Link to subject assignments (combine all assignment types)
                subject_taught = []
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Add lecture assignments if they exist
                    if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                        subject_taught.append(lecture_assignments[(teacher, subj, d, s)])
                    
                    # Add tutorial assignments if they exist
                    if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                        subject_taught.append(tutorial_assignments[(teacher, subj, d, s)])
                    
                    # Add practical assignments if they exist
                    if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                        subject_taught.append(practical_assignments[(teacher, subj, d, s)])
                
                if subject_taught:
                    model.Add(sum(subject_taught) >= 1).OnlyEnforceIf(teacher_teaching[(teacher, d, s)])
                    model.Add(sum(subject_taught) == 0).OnlyEnforceIf(teacher_teaching[(teacher, d, s)].Not())
                else:
                    model.Add(teacher_teaching[(teacher, d, s)] == 0)

    # Add constraints
    
    # Ensure each type of session gets the required number of slots
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            key = (teacher, subj)
            # Constraint for lecture hours
            if subject_lecture_slots[key] > 0:
                lecture_vars = [lecture_assignments[(teacher, subj, d, s)]
                              for d in range(len(days)) for s in range(num_slots)
                              if (teacher, subj, d, s) in lecture_assignments]
                if lecture_vars:
                    model.Add(sum(lecture_vars) == subject_lecture_slots[key])
            
            # Constraint for tutorial hours
            if subject_tutorial_slots[key] > 0:
                tutorial_vars = [tutorial_assignments[(teacher, subj, d, s)]
                               for d in range(len(days)) for s in range(num_slots)
                               if (teacher, subj, d, s) in tutorial_assignments]
                if tutorial_vars:
                    model.Add(sum(tutorial_vars) == subject_tutorial_slots[key])
            
            # Constraint for practical hours
            if subject_practical_slots[key] > 0:
                practical_vars = [practical_assignments[(teacher, subj, d, s)]
                                for d in range(len(days)) for s in range(num_slots)
                                if (teacher, subj, d, s) in practical_assignments]
                if practical_vars:
                    model.Add(sum(practical_vars) == subject_practical_slots[key])
    
    # Ensure practical sessions get consecutive slots
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            key = (teacher, subj)
            if subject_consecutive_slots.get(key, False):
                practical_hours = subject_practical_hours.get(key, 0)
                if practical_hours > 0:
                    # For each practical session start, ensure the next slot is also assigned to the same subject
                    for d in range(len(days)):
                        for s in range(num_slots-1):
                            # If this is the start of a practical session
                            model.Add(practical_assignments[(teacher, subj, d, s)] == 1).OnlyEnforceIf(practical_sessions[(teacher, subj, d, s)])
                            model.Add(practical_assignments[(teacher, subj, d, s+1)] == 1).OnlyEnforceIf(practical_sessions[(teacher, subj, d, s)])
                    
                    # Ensure we have the correct number of practical sessions (each is 2 consecutive slots)
                    if practical_hours >= 2:
                        model.Add(sum(practical_sessions[(teacher, subj, d, s)] 
                                    for d in range(len(days)) for s in range(num_slots-1)) == practical_hours // 2)

    # Ensure a teacher can only teach one subject per time slot
    for teacher in teachers:
        for d in range(len(days)):
            for s in range(num_slots):
                all_assignments = []
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Collect all types of assignments for this slot
                    if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                        all_assignments.append(lecture_assignments[(teacher, subj, d, s)])
                    if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                        all_assignments.append(tutorial_assignments[(teacher, subj, d, s)])
                    if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                        all_assignments.append(practical_assignments[(teacher, subj, d, s)])
                
                if all_assignments:
                    model.Add(sum(all_assignments) <= 1)
    
    # NEW CONSTRAINT: No more than MAX_CONSECUTIVE_SLOTS consecutive teaching slots
    for teacher in teachers:
        for d in range(len(days)):
            # Check each possible sequence of MAX_CONSECUTIVE_SLOTS+1 consecutive slots
            for s_start in range(num_slots - MAX_CONSECUTIVE_SLOTS):
                consecutive_vars = []
                for s in range(s_start, s_start + MAX_CONSECUTIVE_SLOTS + 1):
                    consecutive_vars.append(teacher_teaching[(teacher, d, s)])
                
                # At least one of the MAX_CONSECUTIVE_SLOTS+1 consecutive slots must be free
                model.Add(sum(consecutive_vars) <= MAX_CONSECUTIVE_SLOTS)

    for teacher in teachers:
        for d in range(len(days)):
            
            is_cat = {}
            for cat in range(3):  # Morning, Afternoon, Evening
                cat_slots = [s for s in range(num_slots) if slot_categories[s] == cat]
                is_cat[cat] = model.NewBoolVar(f'{teacher}_day{d}_uses_cat{cat}')

                category_usage = []
                for s in cat_slots:
                    for subj in teacher_subjects[teacher]:
                        key = (teacher, subj)
                        # Add all types of assignments
                        if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                            category_usage.append(lecture_assignments[(teacher, subj, d, s)])
                        if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                            category_usage.append(tutorial_assignments[(teacher, subj, d, s)])
                        if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                            category_usage.append(practical_assignments[(teacher, subj, d, s)])

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

    # Add constraints for free slots based on slot type
    for teacher in teachers:
        for d in range(len(days)):
            # For slot type A (0): slot4 to slot6 should have one free slot
            a_type_constraints = model.NewBoolVar(f'{teacher}_day{d}_A_type_constraints')
            model.Add(teacher_day_category[(teacher, d)] == 0).OnlyEnforceIf(a_type_constraints)
            model.Add(teacher_day_category[(teacher, d)] != 0).OnlyEnforceIf(a_type_constraints.Not())
            
            # For type A, slots 3, 4, 5 (slot4, slot5, slot6 in 1-indexed notation)
            # We need at least one of them to be free
            type_a_slots = [3, 4, 5]
            slot_occupied = []
            for s in type_a_slots:
                is_occupied = model.NewBoolVar(f'{teacher}_day{d}_slot{s}_occupied')
                slot_assignments = []
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Add all types of assignments
                    if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                        slot_assignments.append(lecture_assignments[(teacher, subj, d, s)])
                    if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                        slot_assignments.append(tutorial_assignments[(teacher, subj, d, s)])
                    if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                        slot_assignments.append(practical_assignments[(teacher, subj, d, s)])
                
                if slot_assignments:
                    model.Add(sum(slot_assignments) >= 1).OnlyEnforceIf(is_occupied)
                    model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(is_occupied.Not())
                else:
                    model.Add(is_occupied == 0)
                
                slot_occupied.append(is_occupied)
            
            # Ensure at least one slot is free
            model.Add(sum(slot_occupied) <= len(type_a_slots) - 1).OnlyEnforceIf(a_type_constraints)
            
            # For slot type B (2): slot2 to slot4 should have one free slot
            b_type_constraints = model.NewBoolVar(f'{teacher}_day{d}_B_type_constraints')
            model.Add(teacher_day_category[(teacher, d)] == 2).OnlyEnforceIf(b_type_constraints)
            model.Add(teacher_day_category[(teacher, d)] != 2).OnlyEnforceIf(b_type_constraints.Not())
            
            # For type B, slots 1, 2, 3 (slot2, slot3, slot4 in 1-indexed notation)
            type_b_slots = [1, 2, 3]
            slot_occupied = []
            for s in type_b_slots:
                is_occupied = model.NewBoolVar(f'{teacher}_day{d}_slot{s}_occupied')
                slot_assignments = []
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Add all types of assignments
                    if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                        slot_assignments.append(lecture_assignments[(teacher, subj, d, s)])
                    if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                        slot_assignments.append(tutorial_assignments[(teacher, subj, d, s)])
                    if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                        slot_assignments.append(practical_assignments[(teacher, subj, d, s)])
                
                if slot_assignments:
                    model.Add(sum(slot_assignments) >= 1).OnlyEnforceIf(is_occupied)
                    model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(is_occupied.Not())
                else:
                    model.Add(is_occupied == 0)
                
                slot_occupied.append(is_occupied)
            
            # Ensure at least one slot is free
            model.Add(sum(slot_occupied) <= len(type_b_slots) - 1).OnlyEnforceIf(b_type_constraints)
            
            # For slot type C (1): slot1 to slot2 should have one free slot
            c_type_constraints = model.NewBoolVar(f'{teacher}_day{d}_C_type_constraints')
            model.Add(teacher_day_category[(teacher, d)] == 1).OnlyEnforceIf(c_type_constraints)
            model.Add(teacher_day_category[(teacher, d)] != 1).OnlyEnforceIf(c_type_constraints.Not())
            
            # For type C, slots 0, 1 (slot1, slot2 in 1-indexed notation)
            type_c_slots = [0, 1]
            slot_occupied = []
            for s in type_c_slots:
                is_occupied = model.NewBoolVar(f'{teacher}_day{d}_slot{s}_occupied')
                slot_assignments = []
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Add all types of assignments
                    if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                        slot_assignments.append(lecture_assignments[(teacher, subj, d, s)])
                    if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                        slot_assignments.append(tutorial_assignments[(teacher, subj, d, s)])
                    if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                        slot_assignments.append(practical_assignments[(teacher, subj, d, s)])
                
                if slot_assignments:
                    model.Add(sum(slot_assignments) >= 1).OnlyEnforceIf(is_occupied)
                    model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(is_occupied.Not())
                else:
                    model.Add(is_occupied == 0)
                
                slot_occupied.append(is_occupied)
            
            # Ensure at least one slot is free
            model.Add(sum(slot_occupied) <= len(type_c_slots) - 1).OnlyEnforceIf(c_type_constraints)



    
    for teacher in teachers:
        for d in range(len(days)):
            day_slots = []
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Add all types of assignments
                    if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                        day_slots.append(lecture_assignments[(teacher, subj, d, s)])
                    if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                        day_slots.append(tutorial_assignments[(teacher, subj, d, s)])
                    if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                        day_slots.append(practical_assignments[(teacher, subj, d, s)])
            
            model.Add(sum(day_slots) <= MAX_HOURS_PER_DAY)

 
    for teacher in teachers:
        # Each teacher is either in Mon-Fri batch or Tue-Sat batch
        mon_to_fri = model.NewBoolVar(f'{teacher}_mon_to_fri')
        
        for d in range(len(days)):
            day_slots = []
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Add all types of assignments
                    if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                        day_slots.append(lecture_assignments[(teacher, subj, d, s)])
                    if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                        day_slots.append(tutorial_assignments[(teacher, subj, d, s)])
                    if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                        day_slots.append(practical_assignments[(teacher, subj, d, s)])
            
            # If Mon-Fri batch, no teaching on Saturday (d=5)
            if d == 5:  # Saturday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(mon_to_fri)
            
            # If Tue-Sat batch, no teaching on Monday (d=0)
            elif d == 0:  # Monday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(mon_to_fri.Not())
            
            # Maintain the MAX_HOURS_PER_DAY constraint
            model.Add(sum(day_slots) <= MAX_HOURS_PER_DAY)

    
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    
    timetables = {}
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        for teacher in teachers:
            timetable = []
            for d in range(len(days)):
                row = [teacher, days[d]]
                
                for s in range(num_slots):
                    cell_value = ""
                    for subj in teacher_subjects[teacher]:
                        key = (teacher, subj)
                        # Check for lecture assignments
                        if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments and solver.Value(lecture_assignments[(teacher, subj, d, s)]):
                            cell_value = f"{subj} (Lecture)"
                            break
                        
                        # Check for tutorial assignments
                        if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments and solver.Value(tutorial_assignments[(teacher, subj, d, s)]):
                            cell_value = f"{subj} (Tutorial)"
                            break
                        
                        # Check for practical assignments
                        if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments and solver.Value(practical_assignments[(teacher, subj, d, s)]):
                            # Check if this is part of a practical session
                            if s > 0 and (teacher, subj, d, s-1) in practical_assignments and solver.Value(practical_assignments[(teacher, subj, d, s-1)]):
                                cell_value = f"{subj} (Practical)"
                            # Check if this is the start of a practical session
                            elif s < num_slots-1 and (teacher, subj, d, s+1) in practical_assignments and solver.Value(practical_assignments[(teacher, subj, d, s+1)]):
                                cell_value = f"{subj} (Practical)"
                            else:
                                cell_value = f"{subj} (Practical)"
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
            sheet_name = teacher[:31]  # Excel has a 31-character limit for sheet names
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file