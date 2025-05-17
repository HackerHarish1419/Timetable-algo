import pandas as pd
from ortools.sat.python import cp_model
import logging

MAX_HOURS_PER_DAY = 5
MAX_CONSECUTIVE_SLOTS = 2  # Maximum consecutive teaching slots
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
    
    # Create dictionaries for hours
    subject_lecture_hours = dict(zip(df['Subject'], df['lecture_hours']))
    subject_tutorial_hours = dict(zip(df['Subject'], df['tutorial_hours']))
    subject_practical_hours = dict(zip(df['Subject'], df['practical_hours']))
    subject_credits = dict(zip(df['Subject'], df['credits']))
    
    teacher_subjects = {teacher: df[df['Faculty'] == teacher]['Subject'].unique().tolist()
                        for teacher in teachers}

    # Creating a dictionary to track which teachers can teach which subjects
    qualified_teachers = {}
    for subj in df['Subject'].unique():
        qualified_teachers[subj] = df[df['Subject'] == subj]['Faculty'].unique().tolist()

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] 
    num_slots = 7
    all_slots = [(d, s) for d in range(len(days)) for s in range(num_slots)]

    # Calculate weekly slots needed for each subject based on lecture, tutorial, and practical hours
    subject_weekly_slots = {}
    subject_consecutive_slots = {}  # To track which subjects need consecutive slots

    # Track which subjects have practical hours (for batch splitting)
    subjects_with_practicals = []
    
    for subj in df['Subject'].unique():
        # Get the subject data
        subj_data = df[df['Subject'] == subj].iloc[0]
        
        # Weekly slots for lectures
        lecture_slots = subj_data['lecture_hours']
        
        # Weekly slots for tutorials
        tutorial_slots = subj_data['tutorial_hours']
        
        # Weekly slots for practicals (these will need consecutive scheduling)
        practical_hours = subj_data['practical_hours']
        
        # If there are practical hours, we need to double them for the two batches
        if practical_hours > 0:
            subjects_with_practicals.append(subj)
            practical_slots = practical_hours * 2 * 2  # Double for consecutive slots, double for two batches
        else:
            practical_slots = 0
            
        # Total weekly slots (without practicals as they'll be handled separately)
        total_slots = lecture_slots + tutorial_slots
        
        subject_weekly_slots[subj] = int(total_slots)
        
        # Mark if this subject has practicals (needs consecutive slots)
        subject_consecutive_slots[subj] = practical_hours > 0

    slot_categories = {
        0: 0, 1: 0, 2: 0,  # Morning
        3: 1, 4: 1,        # Afternoon
        5: 2, 6: 2         # Evening
    }

    model = cp_model.CpModel()

    # Define variables
    
    subject_assignments = {}
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            for d in range(len(days)):
                for s in range(num_slots):
                    subject_assignments[(teacher, subj, d, s)] = model.NewBoolVar(
                        f'{teacher}_{subj}_day{d}_slot{s}')

    # For practical sessions (need consecutive slots)
    # Now we need to track batches separately
    practical_batch_assignments = {}
    for subj in subjects_with_practicals:
        practical_hours = subject_practical_hours.get(subj, 0)
        if practical_hours > 0:
            for batch in [1, 2]:  # Two batches
                for teacher in qualified_teachers[subj]:
                    for d in range(len(days)):
                        # We can only start a practical session up to slot num_slots-2 to ensure there's room for 2 consecutive slots
                        for s in range(num_slots-1):
                            practical_batch_assignments[(subj, batch, teacher, d, s)] = model.NewBoolVar(
                                f'{subj}_batch{batch}_{teacher}_day{d}_slot{s}')

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
                
                # Link to subject assignments
                subject_taught = []
                for subj in teacher_subjects[teacher]:
                    subject_taught.append(subject_assignments[(teacher, subj, d, s)])
                
                if subject_taught:
                    model.Add(sum(subject_taught) >= 1).OnlyEnforceIf(teacher_teaching[(teacher, d, s)])
                    model.Add(sum(subject_taught) == 0).OnlyEnforceIf(teacher_teaching[(teacher, d, s)].Not())
                else:
                    model.Add(teacher_teaching[(teacher, d, s)] == 0)

    # Add constraints
    
    # Ensure subjects get their required number of weekly slots (excluding practicals)
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            weekly_slots = subject_weekly_slots[subj]
            model.Add(sum(subject_assignments[(teacher, subj, d, s)]
                          for d in range(len(days)) for s in range(num_slots)) == weekly_slots)
    
    # NEW: Handle practical sessions with batch splitting
    for subj in subjects_with_practicals:
        practical_hours = subject_practical_hours.get(subj, 0)
        if practical_hours > 0:
            # Each batch needs practical_hours number of lab slots (in pairs of consecutive slots)
            practical_sessions_per_batch = practical_hours
            
            # Ensure exactly practical_hours practical sessions are scheduled for each batch
            for batch in [1, 2]:
                model.Add(sum(practical_batch_assignments[(subj, batch, teacher, d, s)]
                              for teacher in qualified_teachers[subj]
                              for d in range(len(days))
                              for s in range(num_slots-1)) == practical_sessions_per_batch)
            
            # Connect practical batch assignments to subject assignments
            for batch in [1, 2]:
                for teacher in qualified_teachers[subj]:
                    for d in range(len(days)):
                        for s in range(num_slots-1):
                            # If this practical batch is assigned here, the teacher is teaching this subject
                            # and we need to ensure consecutive slots
                            model.Add(subject_assignments[(teacher, subj, d, s)] == 1).OnlyEnforceIf(
                                practical_batch_assignments[(subj, batch, teacher, d, s)])
                            model.Add(subject_assignments[(teacher, subj, d, s+1)] == 1).OnlyEnforceIf(
                                practical_batch_assignments[(subj, batch, teacher, d, s)])

    # Constraint: One teacher cannot handle both batches of the same subject by default
    # But if they have free slots, they can be assigned both batches
    for subj in subjects_with_practicals:
        practical_hours = subject_practical_hours.get(subj, 0)
        if practical_hours > 0:
            # Try to assign Batch 1 to the primary teacher
            primary_teacher = df[df['Subject'] == subj].iloc[0]['Faculty']
            
            # Variables to track if each batch is assigned to the primary teacher
            batch1_primary = model.NewBoolVar(f'{subj}_batch1_primary')
            batch2_primary = model.NewBoolVar(f'{subj}_batch2_primary')
            
            # Connect these variables to the practical batch assignments
            model.Add(sum(practical_batch_assignments[(subj, 1, primary_teacher, d, s)]
                          for d in range(len(days))
                          for s in range(num_slots-1)) >= 1).OnlyEnforceIf(batch1_primary)
            model.Add(sum(practical_batch_assignments[(subj, 1, primary_teacher, d, s)]
                          for d in range(len(days))
                          for s in range(num_slots-1)) == 0).OnlyEnforceIf(batch1_primary.Not())
            
            model.Add(sum(practical_batch_assignments[(subj, 2, primary_teacher, d, s)]
                          for d in range(len(days))
                          for s in range(num_slots-1)) >= 1).OnlyEnforceIf(batch2_primary)
            model.Add(sum(practical_batch_assignments[(subj, 2, primary_teacher, d, s)]
                          for d in range(len(days))
                          for s in range(num_slots-1)) == 0).OnlyEnforceIf(batch2_primary.Not())
            
            # Force Batch 1 to be assigned to the primary teacher
            model.Add(batch1_primary == 1)
            
            # Try to assign Batch 2 to the primary teacher if possible
            # This is a soft constraint - we'll add an incentive to the objective function later
            
            # Ensure that batches don't overlap in time
            for d in range(len(days)):
                for s in range(num_slots-1):
                    # For each possible starting slot of a practical session
                    batch1_session_vars = []
                    batch2_session_vars = []
                    
                    for teacher in qualified_teachers[subj]:
                        batch1_session_vars.append(practical_batch_assignments[(subj, 1, teacher, d, s)])
                        batch2_session_vars.append(practical_batch_assignments[(subj, 2, teacher, d, s)])
                    
                    # At most one batch can start at this slot
                    model.Add(sum(batch1_session_vars + batch2_session_vars) <= 1)

    # Ensure a teacher can only teach one subject per time slot
    for teacher in teachers:
        for d in range(len(days)):
            for s in range(num_slots):
                model.Add(sum(subject_assignments[(teacher, subj, d, s)]
                              for subj in teacher_subjects[teacher]) <= 1)

    # No more than MAX_CONSECUTIVE_SLOTS consecutive teaching slots
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
                    slot_assignments.append(subject_assignments[(teacher, subj, d, s)])
                
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
                    slot_assignments.append(subject_assignments[(teacher, subj, d, s)])
                
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
                    slot_assignments.append(subject_assignments[(teacher, subj, d, s)])
                
                if slot_assignments:
                    model.Add(sum(slot_assignments) >= 1).OnlyEnforceIf(is_occupied)
                    model.Add(sum(slot_assignments) == 0).OnlyEnforceIf(is_occupied.Not())
                else:
                    model.Add(is_occupied == 0)
                
                slot_occupied.append(is_occupied)
            
            # Ensure at least one slot is free
            model.Add(sum(slot_occupied) <= len(type_c_slots) - 1).OnlyEnforceIf(c_type_constraints)


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

    # Add maximum teaching hours per day constraint
    for teacher in teachers:
        for d in range(len(days)):
            day_slots = []
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    day_slots.append(subject_assignments[(teacher, subj, d, s)])
            model.Add(sum(day_slots) <= MAX_HOURS_PER_DAY)

    # Each teacher is either in Mon-Fri batch or Tue-Sat batch
    for teacher in teachers:
        mon_to_fri = model.NewBoolVar(f'{teacher}_mon_to_fri')
        
        for d in range(len(days)):
            day_slots = []
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    day_slots.append(subject_assignments[(teacher, subj, d, s)])
            
            # If Mon-Fri batch, no teaching on Saturday (d=5)
            if d == 5:  # Saturday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(mon_to_fri)
            
            # If Tue-Sat batch, no teaching on Monday (d=0)
            elif d == 0:  # Monday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(mon_to_fri.Not())
            
            # Maintain the MAX_HOURS_PER_DAY constraint
            model.Add(sum(day_slots) <= MAX_HOURS_PER_DAY)

    add_open_elective_constraints(model, subject_assignments, teachers, days, num_slots)

    # Create an objective function to prefer primary teacher for batch 2 when possible
    objective_terms = []
    
    # Add a penalty for assigning batch 2 to secondary teachers
    for subj in subjects_with_practicals:
        primary_teacher = df[df['Subject'] == subj].iloc[0]['Faculty']
        
        # For each practical session of batch 2
        practical_hours = subject_practical_hours.get(subj, 0)
        if practical_hours > 0:
            for d in range(len(days)):
                for s in range(num_slots-1):
                    # Add a reward for using the primary teacher for batch 2
                    primary_batch2 = practical_batch_assignments.get((subj, 2, primary_teacher, d, s))
                    if primary_batch2:
                        # Add a large bonus to prioritize using the primary teacher
                        objective_terms.append(100 * primary_batch2)
    
    # Set the objective function (maximize the terms)
    if objective_terms:
        model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    timetables = {}
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        # Track which teachers and batches are assigned to each practical course
        practical_assignments = {}
        for subj in subjects_with_practicals:
            practical_assignments[subj] = {1: set(), 2: set()}
            for batch in [1, 2]:
                for teacher in qualified_teachers[subj]:
                    for d in range(len(days)):
                        for s in range(num_slots-1):
                            if (subj, batch, teacher, d, s) in practical_batch_assignments:
                                if solver.Value(practical_batch_assignments[(subj, batch, teacher, d, s)]):
                                    practical_assignments[subj][batch].add(teacher)
                                    logging.info(f"Practical Assignment: {subj} Batch {batch} assigned to {teacher} on {days[d]} slots {s},{s+1}")
        
        for teacher in teachers:
            timetable = []
            for d in range(len(days)):
                row = [teacher, days[d]]
                
                for s in range(num_slots):
                    cell_value = ""
                    for subj in teacher_subjects[teacher]:
                        if solver.Value(subject_assignments[(teacher, subj, d, s)]):
                            # Check if this is part of a practical session
                            batch_info = ""
                            if subject_consecutive_slots.get(subj, False):
                                # Check if this is a practical session start
                                for batch in [1, 2]:
                                    if s > 0 and (subj, batch, teacher, d, s-1) in practical_batch_assignments:
                                        if solver.Value(practical_batch_assignments[(subj, batch, teacher, d, s-1)]):
                                            batch_info = f" (Lab-B{batch})"
                                    elif s < num_slots-1 and (subj, batch, teacher, d, s) in practical_batch_assignments:
                                        if solver.Value(practical_batch_assignments[(subj, batch, teacher, d, s)]):
                                            batch_info = f" (Lab-B{batch})"
                            
                            cell_value = f"{subj}{batch_info}"
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
            sheet_name = teacher[:31]  
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file