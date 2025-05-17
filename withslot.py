import pandas as pd
from ortools.sat.python import cp_model
import logging

MAX_HOURS_PER_DAY = 5
MAX_CONSECUTIVE_SLOTS = 2  # Maximum consecutive teaching slots

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Define slot timings based on the image
THEORY_SLOTS = {
    'T1': '8.00-8.50',
    'T2': '9.00-9.50',
    'T3': '10.00-10.50',
    'T4': '11.00-11.50',
    'T5/T6': '12.00-12.50',
    'T7': '1.00-1.50',
    'T8': '2.00-2.50',
    'T9': '3.00-3.50',
    'T10': '4.00-4.50',
    'T11': '5.10-6.00',
    'T12': '6.10-7.00'
}

LAB_SLOTS = {
    'L1': '8.00-8.50/8.50-9.40',
    'L2': '10.00-10.50/10.50-11.40',
    'L3': '11.40-12.30/12.30-1.20',
    'L4': '1.20-2.10/2.10-3.00',
    'L5': '3.00-3.50/3.50-4.40',
    'L6': '5.10-6.00/6.00-6.50'
}

# Define slot types with their associated theory and lab slots
SLOT_TYPES = {
    'A': {'theory': ['T1', 'T2', 'T3', 'T4', 'T5/T6', 'T7', 'T8'], 'lab': ['L1', 'L2', 'L3', 'L4'], 'range': '8–3'},
    'B': {'theory': ['T3', 'T4', 'T5/T6', 'T7', 'T8', 'T9', 'T10'], 'lab': ['L2', 'L3', 'L4', 'L5'], 'range': '10–5'},
    'C': {'theory': ['T5/T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12'], 'lab': ['L4', 'L5', 'L6'], 'range': '12–7'}
}

# Map numeric indices to slot types
SLOT_TYPE_MAP = {
    0: 'A',  # Morning (8-3)
    1: 'B',  # Afternoon (10-5)
    2: 'C'   # Evening (12-7)
}

# List of theory and lab slots for display
DISPLAY_THEORY_SLOTS = ['T1', 'T2', 'T3', 'T4', 'T5/T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12']
DISPLAY_LAB_SLOTS = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6']

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
    
    # Use the slot names as defined in the image
    theory_slot_names = list(THEORY_SLOTS.keys())
    lab_slot_names = list(LAB_SLOTS.keys())
    
    # Calculate total number of slots
    num_slots = len(theory_slot_names)  # Use theory slots as they cover all time periods
    
    # Calculate weekly slots needed for each subject based on lecture, tutorial, and practical hours
    subject_weekly_slots = {}
    subject_lecture_slots = {}    # To track lecture slots needed
    subject_tutorial_slots = {}   # To track tutorial slots needed
    subject_practical_slots = {}  # To track practical slots needed
    subject_consecutive_slots = {}  # To track which subjects need consecutive slots

    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            key = (teacher, subj)
            
            # Weekly slots for lectures (store separately)
            lecture_slots = subject_lecture_hours[key]
            subject_lecture_slots[key] = lecture_slots
            
            # Weekly slots for tutorials (store separately)
            tutorial_slots = subject_tutorial_hours[key]
            subject_tutorial_slots[key] = tutorial_slots
            
            # Weekly slots for practicals (store separately)
            practical_slots = subject_practical_hours[key]
            subject_practical_slots[key] = practical_slots
            
            # Total weekly slots
            total_slots = lecture_slots + tutorial_slots + practical_slots
            
            subject_weekly_slots[key] = total_slots
            
            # Mark if this subject has practicals (needs consecutive slots)
            subject_consecutive_slots[key] = practical_slots > 0

    model = cp_model.CpModel()

    # Define variables
    
    # Split assignment variables by type
    lecture_assignments = {}     # For lecture hours
    tutorial_assignments = {}    # For tutorial hours 
    practical_assignments = {}   # For practical hours
    
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            key = (teacher, subj)
            
            # Only create lecture assignment variables if lecture hours > 0
            if subject_lecture_slots[key] > 0:
                for d in range(len(days)):
                    for s, slot_name in enumerate(theory_slot_names):
                        lecture_assignments[(teacher, subj, d, s)] = model.NewBoolVar(
                            f'{teacher}_{subj}_lecture_day{d}_slot{s}')
            
            # Only create tutorial assignment variables if tutorial hours > 0
            if subject_tutorial_slots[key] > 0:
                for d in range(len(days)):
                    for s, slot_name in enumerate(theory_slot_names):
                        tutorial_assignments[(teacher, subj, d, s)] = model.NewBoolVar(
                            f'{teacher}_{subj}_tutorial_day{d}_slot{s}')
            
            # Only create practical assignment variables if practical hours > 0
            if subject_practical_slots[key] > 0:
                for d in range(len(days)):
                    for s, slot_name in enumerate(lab_slot_names):
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
                    for s in range(len(lab_slot_names)-1):
                        practical_sessions[(teacher, subj, d, s)] = model.NewBoolVar(
                            f'{teacher}_{subj}_practical_day{d}_slot{s}')

    # Teacher day slot type (A, B, or C)
    teacher_day_slot_type = {}
    for teacher in teachers:
        for d in range(len(days)):
            # 0 = A, 1 = B, 2 = C
            teacher_day_slot_type[(teacher, d)] = model.NewIntVar(0, 2, f'{teacher}_day{d}_slot_type')

    # Teacher teaching in a slot (any subject)
    teacher_teaching = {}
    for teacher in teachers:
        for d in range(len(days)):
            # For theory slots
            for s, slot_name in enumerate(theory_slot_names):
                teacher_teaching[(teacher, d, 'theory', s)] = model.NewBoolVar(f'{teacher}_teaching_theory_day{d}_slot{s}')
                
                # Link to subject assignments (combine lecture and tutorial)
                subject_taught = []
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Add lecture assignments if they exist
                    if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                        subject_taught.append(lecture_assignments[(teacher, subj, d, s)])
                    
                    # Add tutorial assignments if they exist
                    if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                        subject_taught.append(tutorial_assignments[(teacher, subj, d, s)])
                
                if subject_taught:
                    model.Add(sum(subject_taught) >= 1).OnlyEnforceIf(teacher_teaching[(teacher, d, 'theory', s)])
                    model.Add(sum(subject_taught) == 0).OnlyEnforceIf(teacher_teaching[(teacher, d, 'theory', s)].Not())
                else:
                    model.Add(teacher_teaching[(teacher, d, 'theory', s)] == 0)
            
            # For lab slots
            for s, slot_name in enumerate(lab_slot_names):
                teacher_teaching[(teacher, d, 'lab', s)] = model.NewBoolVar(f'{teacher}_teaching_lab_day{d}_slot{s}')
                
                # Link to practical assignments
                subject_taught = []
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Add practical assignments if they exist
                    if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                        subject_taught.append(practical_assignments[(teacher, subj, d, s)])
                
                if subject_taught:
                    model.Add(sum(subject_taught) >= 1).OnlyEnforceIf(teacher_teaching[(teacher, d, 'lab', s)])
                    model.Add(sum(subject_taught) == 0).OnlyEnforceIf(teacher_teaching[(teacher, d, 'lab', s)].Not())
                else:
                    model.Add(teacher_teaching[(teacher, d, 'lab', s)] == 0)

    # Add constraints
    
    # Ensure each type of session gets the required number of slots
    for teacher in teachers:
        for subj in teacher_subjects[teacher]:
            key = (teacher, subj)
            # Constraint for lecture hours
            if subject_lecture_slots[key] > 0:
                lecture_vars = [lecture_assignments[(teacher, subj, d, s)]
                              for d in range(len(days)) for s in range(len(theory_slot_names))
                              if (teacher, subj, d, s) in lecture_assignments]
                if lecture_vars:
                    model.Add(sum(lecture_vars) == subject_lecture_slots[key])
            
            # Constraint for tutorial hours
            if subject_tutorial_slots[key] > 0:
                tutorial_vars = [tutorial_assignments[(teacher, subj, d, s)]
                               for d in range(len(days)) for s in range(len(theory_slot_names))
                               if (teacher, subj, d, s) in tutorial_assignments]
                if tutorial_vars:
                    model.Add(sum(tutorial_vars) == subject_tutorial_slots[key])
            
            # Constraint for practical hours
            if subject_practical_slots[key] > 0:
                practical_vars = [practical_assignments[(teacher, subj, d, s)]
                                for d in range(len(days)) for s in range(len(lab_slot_names))
                                if (teacher, subj, d, s) in practical_assignments]
                if practical_vars:
                    model.Add(sum(practical_vars) == subject_practical_slots[key])
    
    # Ensure practical sessions get consecutive slots (if needed)
    # This depends on how practicals are actually handled in your institution
    # For now, assuming each practical takes one lab slot
    
    # Ensure a teacher can only teach one subject per time slot
    for teacher in teachers:
        for d in range(len(days)):
            # For theory slots
            for s in range(len(theory_slot_names)):
                theory_assignments = []
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Collect lecture and tutorial assignments for this slot
                    if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                        theory_assignments.append(lecture_assignments[(teacher, subj, d, s)])
                    if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                        theory_assignments.append(tutorial_assignments[(teacher, subj, d, s)])
                
                if theory_assignments:
                    model.Add(sum(theory_assignments) <= 1)
            
            # For lab slots
            for s in range(len(lab_slot_names)):
                lab_assignments = []
                for subj in teacher_subjects[teacher]:
                    key = (teacher, subj)
                    # Collect practical assignments for this slot
                    if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                        lab_assignments.append(practical_assignments[(teacher, subj, d, s)])
                
                if lab_assignments:
                    model.Add(sum(lab_assignments) <= 1)
    
    # No more than MAX_CONSECUTIVE_SLOTS consecutive teaching slots
    for teacher in teachers:
        for d in range(len(days)):
            # For theory slots
            for s_start in range(len(theory_slot_names) - MAX_CONSECUTIVE_SLOTS):
                consecutive_vars = []
                for s in range(s_start, s_start + MAX_CONSECUTIVE_SLOTS + 1):
                    consecutive_vars.append(teacher_teaching[(teacher, d, 'theory', s)])
                
                # At least one of the MAX_CONSECUTIVE_SLOTS+1 consecutive slots must be free
                model.Add(sum(consecutive_vars) <= MAX_CONSECUTIVE_SLOTS)
            
            # For lab slots
            for s_start in range(len(lab_slot_names) - MAX_CONSECUTIVE_SLOTS):
                consecutive_vars = []
                for s in range(s_start, s_start + MAX_CONSECUTIVE_SLOTS + 1):
                    consecutive_vars.append(teacher_teaching[(teacher, d, 'lab', s)])
                
                # At least one of the MAX_CONSECUTIVE_SLOTS+1 consecutive slots must be free
                model.Add(sum(consecutive_vars) <= MAX_CONSECUTIVE_SLOTS)

    # Slot type constraints
    for teacher in teachers:
        for d in range(len(days)):
            # For each slot type (A, B, C)
            for slot_type_idx, slot_type in enumerate(SLOT_TYPE_MAP.values()):
                is_this_slot_type = model.NewBoolVar(f'{teacher}_day{d}_is_{slot_type}')
                model.Add(teacher_day_slot_type[(teacher, d)] == slot_type_idx).OnlyEnforceIf(is_this_slot_type)
                model.Add(teacher_day_slot_type[(teacher, d)] != slot_type_idx).OnlyEnforceIf(is_this_slot_type.Not())
                
                # If this day is slot type A/B/C, ensure theory assignments only happen in allowed theory slots
                allowed_theory_slots = SLOT_TYPES[slot_type]['theory']
                for s, slot_name in enumerate(theory_slot_names):
                    is_slot_allowed = slot_name in allowed_theory_slots
                    
                    for subj in teacher_subjects[teacher]:
                        key = (teacher, subj)
                        
                        # For lecture assignments
                        if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments:
                            if not is_slot_allowed:
                                model.Add(lecture_assignments[(teacher, subj, d, s)] == 0).OnlyEnforceIf(is_this_slot_type)
                        
                        # For tutorial assignments
                        if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments:
                            if not is_slot_allowed:
                                model.Add(tutorial_assignments[(teacher, subj, d, s)] == 0).OnlyEnforceIf(is_this_slot_type)
                
                # If this day is slot type A/B/C, ensure practical assignments only happen in allowed lab slots
                allowed_lab_slots = SLOT_TYPES[slot_type]['lab']
                for s, slot_name in enumerate(lab_slot_names):
                    is_slot_allowed = slot_name in allowed_lab_slots
                    
                    for subj in teacher_subjects[teacher]:
                        key = (teacher, subj)
                        
                        # For practical assignments
                        if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments:
                            if not is_slot_allowed:
                                model.Add(practical_assignments[(teacher, subj, d, s)] == 0).OnlyEnforceIf(is_this_slot_type)

    # Maximum teaching hours per day
    for teacher in teachers:
        for d in range(len(days)):
            # Count all teaching slots (theory and lab) for this day
            day_slots = []
            
            # Add theory teaching slots
            for s in range(len(theory_slot_names)):
                day_slots.append(teacher_teaching[(teacher, d, 'theory', s)])
            
            # Add lab teaching slots
            for s in range(len(lab_slot_names)):
                day_slots.append(teacher_teaching[(teacher, d, 'lab', s)])
            
            model.Add(sum(day_slots) <= MAX_HOURS_PER_DAY)

    # Ensure each teacher has a balanced distribution of slot types
    for teacher in teachers:
        for slot_type_idx, slot_type in enumerate(SLOT_TYPE_MAP.values()):
            slot_type_days = []
            for d in range(len(days)):
                is_this_type = model.NewBoolVar(f'{teacher}_day{d}_is_{slot_type}')
                model.Add(teacher_day_slot_type[(teacher, d)] == slot_type_idx).OnlyEnforceIf(is_this_type)
                model.Add(teacher_day_slot_type[(teacher, d)] != slot_type_idx).OnlyEnforceIf(is_this_type.Not())
                slot_type_days.append(is_this_type)
            
            # Each teacher should have at least 1 day and at most 2 days of each slot type (A, B, C)
            model.Add(sum(slot_type_days) >= 1)
            model.Add(sum(slot_type_days) <= 2)

    # Mon-Fri or Tue-Sat working days
    for teacher in teachers:
        # Each teacher is either in Mon-Fri batch or Tue-Sat batch
        mon_to_fri = model.NewBoolVar(f'{teacher}_mon_to_fri')
        
        for d in range(len(days)):
            # Count all teaching slots (theory and lab) for this day
            day_slots = []
            
            # Add theory teaching slots
            for s in range(len(theory_slot_names)):
                day_slots.append(teacher_teaching[(teacher, d, 'theory', s)])
            
            # Add lab teaching slots
            for s in range(len(lab_slot_names)):
                day_slots.append(teacher_teaching[(teacher, d, 'lab', s)])
            
            # If Mon-Fri batch, no teaching on Saturday (d=5)
            if d == 5:  # Saturday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(mon_to_fri)
            
            # If Tue-Sat batch, no teaching on Monday (d=0)
            elif d == 0:  # Monday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(mon_to_fri.Not())

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    # Create timetable output in the specific format requested
    teacher_timetables = {}
    
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        for teacher in teachers:
            # Create separate dataframes for theory and labs
            theory_data = []
            lab_data = []
            
            for d in range(len(days)):
                slot_type_idx = solver.Value(teacher_day_slot_type[(teacher, d)])
                slot_type = SLOT_TYPE_MAP[slot_type_idx]
                slot_type_range = SLOT_TYPES[slot_type]['range']
                
                # Initialize empty row for theory
                theory_row = {
                    "Teacher": f"{teacher} - {days[d]}",
                    "Day": days[d],
                    "SlotType": f"{slot_type} ({slot_type_range})"
                }
                
                # Fill in theory subjects for each slot
                for s, slot_name in enumerate(theory_slot_names):
                    slot_key = f"Slot {s+1}"
                    theory_row[slot_key] = ""
                    
                    # Only include slots that are allowed for this slot type
                    if slot_name in SLOT_TYPES[slot_type]['theory']:
                        for subj in teacher_subjects[teacher]:
                            key = (teacher, subj)
                            
                            # Check for lecture assignments
                            if subject_lecture_slots[key] > 0 and (teacher, subj, d, s) in lecture_assignments and solver.Value(lecture_assignments[(teacher, subj, d, s)]):
                                theory_row[slot_key] = f"{subj} (Lecture)"
                                break
                            
                            # Check for tutorial assignments
                            if subject_tutorial_slots[key] > 0 and (teacher, subj, d, s) in tutorial_assignments and solver.Value(tutorial_assignments[(teacher, subj, d, s)]):
                                theory_row[slot_key] = f"{subj} (Tutorial)"
                                break
                
                # Add theory row to dataset
                theory_data.append(theory_row)
                
                # Initialize empty row for labs
                lab_row = {
                    "Teacher": f"{teacher} - {days[d]}",
                    "Day": days[d],
                    "SlotType": f"{slot_type} ({slot_type_range})"
                }
                
                # Fill in lab subjects for each slot
                for s, slot_name in enumerate(lab_slot_names):
                    slot_key = f"Slot {s+1}"
                    lab_row[slot_key] = ""
                    
                    # Only include slots that are allowed for this slot type
                    if slot_name in SLOT_TYPES[slot_type]['lab']:
                        for subj in teacher_subjects[teacher]:
                            key = (teacher, subj)
                            
                            # Check for practical assignments
                            if subject_practical_slots[key] > 0 and (teacher, subj, d, s) in practical_assignments and solver.Value(practical_assignments[(teacher, subj, d, s)]):
                                lab_row[slot_key] = f"{subj} (Practical)"
                                break
                
                # Add lab row to dataset
                lab_data.append(lab_row)
            
            # Create DataFrames from the data
            theory_df = pd.DataFrame(theory_data)
            lab_df = pd.DataFrame(lab_data)
            
            # Store both dataframes for this teacher
            teacher_timetables[teacher] = {
                'theory': theory_df,
                'lab': lab_df
            }
        
        logging.info("✅ Timetable successfully created")
        return teacher_timetables
    else:
        logging.error(f"❌ No feasible schedule found. Solver status: {solver.StatusName(status)}")
        return None

def format_timetable_for_display(timetables):
    """
    Format the timetable as shown in the requested example format
    """
    if timetables is None:
        return "No timetable data available."
    
    result = []
    
    # Process each teacher's timetable
    for teacher, data in timetables.items():
        # Format theory timetable
        theory_df = data['theory']
        if not theory_df.empty:
            result.append(f"\n{'-'*80}")
            result.append(f"THEORY TIMETABLE FOR {teacher}")
            result.append(f"{'-'*80}")
            
            # Get the slot columns
            slot_cols = [col for col in theory_df.columns if col.startswith("Slot")]
            
            # Create header
            header = "| Teacher | Day | " + " | ".join(slot_cols) + " | SlotType |"
            result.append(header)
            result.append("|" + "-"*len(header.replace("|", "")) + "|")
            
            # Add rows
            for _, row in theory_df.iterrows():
                row_str = f"| {row['Teacher']} | " + " | ".join([str(row[col]) for col in slot_cols]) + f" | {row['SlotType']} |"
                result.append(row_str)
        
        # Format lab timetable
        lab_df = data['lab']
        if not lab_df.empty:
            result.append(f"\n{'-'*80}")
            result.append(f"LAB TIMETABLE FOR {teacher}")
            result.append(f"{'-'*80}")
            
            # Get the slot columns
            slot_cols = [col for col in lab_df.columns if col.startswith("Slot")]
            
            # Create header
            header = "| Teacher | Day | " + " | ".join(slot_cols) + " | SlotType |"
            result.append(header)
            result.append("|" + "-"*len(header.replace("|", "")) + "|")
            
            # Add rows
            for _, row in lab_df.iterrows():
                row_str = f"| {row['Teacher']} | " + " | ".join([str(row[col]) for col in slot_cols]) + f" | {row['SlotType']} |"
                result.append(row_str)
    
    return "\n".join(result)

def export_timetable_to_csv(timetables, output_file="teacher_timetables.csv"):
    """
    Export both theory and lab timetables to a CSV file
    """
    if timetables is None:
        logging.warning("No timetable data to export.")
        return None

    # Concatenate all theory timetables
    theory_dfs = [data['theory'] for teacher, data in timetables.items()]
    theory_df = pd.concat(theory_dfs, ignore_index=True)
    theory_df['Type'] = 'Theory'
    
    # Concatenate all lab timetables
    lab_dfs = [data['lab'] for teacher, data in timetables.items()]
    lab_df = pd.concat(lab_dfs, ignore_index=True)
    lab_df['Type'] = 'Lab'
    
    # Combine theory and lab timetables
    all_timetables = pd.concat([theory_df, lab_df], ignore_index=True)
    
    all_timetables.to_csv(output_file, index=False)
    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file

def export_timetable_to_excel(timetables, output_file="teacher_timetables.xlsx"):
    """
    Export both theory and lab timetables to an Excel file with separate sheets
    """
    if timetables is None:
        logging.warning("No timetable data to export.")
        return None

    with pd.ExcelWriter(output_file) as writer:
        # Create sheets for all teachers combined
        theory_dfs = [data['theory'] for teacher, data in timetables.items()]
        lab_dfs = [data['lab'] for teacher, data in timetables.items()]

        theory_df = pd.concat(theory_dfs, ignore_index=True)
        lab_df = pd.concat(lab_dfs, ignore_index=True)

        theory_df['Type'] = 'Theory'
        lab_df['Type'] = 'Lab'

        # Write combined sheets
        theory_df.to_excel(writer, sheet_name="All Theory", index=False)
        lab_df.to_excel(writer, sheet_name="All Lab", index=False)

        # Write individual teacher sheets
        for teacher, data in timetables.items():
            sheet_name_theory = f"{teacher[:25]}_Theory"  # Excel sheet name limit
            sheet_name_lab = f"{teacher[:25]}_Lab"
            data['theory'].to_excel(writer, sheet_name=sheet_name_theory, index=False)
            data['lab'].to_excel(writer, sheet_name=sheet_name_lab, index=False)

    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file