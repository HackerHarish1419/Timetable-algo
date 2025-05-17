import pandas as pd
from ortools.sat.python import cp_model
import logging
import time
import concurrent.futures
import os
import numpy as np
from tqdm import tqdm

MAX_HOURS_PER_DAY = 5
MORNING_SLOTS = [0, 1, 2]    
SURVEY_LAB_CODE = 'CE23331'  
MAX_TEACHERS_PER_BATCH = 50 # Process teachers in batches for large datasets

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def process_teacher_batch(teacher_batch, df, subject_lecture_hours, subject_tutorial_hours, 
                   subject_practical_hours, subject_weekly_slots, subject_consecutive_slots,
                   teacher_subjects, days, num_slots, slot_categories, teacher_day_preferences=None):
    """Process a batch of teachers to create timetables"""
    logging.info(f"Processing batch of {len(teacher_batch)} teachers")
    
    model = cp_model.CpModel()
    
    # Define variables
    subject_assignments = {}
    practical_sessions = {}
    teacher_day_category = {}
    
    # Initialize variables for all teachers in the batch
    for teacher in teacher_batch:
        for subj in teacher_subjects[teacher]:
            for d in range(len(days)):
                for s in range(num_slots):
                    subject_assignments[(teacher, subj, d, s)] = model.NewBoolVar(
                        f'{teacher}_{subj}_day{d}_slot{s}')

        # For practical sessions (need consecutive slots)
        for subj in teacher_subjects[teacher]:
            if subject_consecutive_slots.get(subj, False):
                for d in range(len(days)):
                    # We can only start a practical session up to slot num_slots-2 to ensure there's room for 2 consecutive slots
                    for s in range(num_slots-1):
                        practical_sessions[(teacher, subj, d, s)] = model.NewBoolVar(
                            f'{teacher}_{subj}_practical_day{d}_slot{s}')

        # For day categories
        for d in range(len(days)):
            teacher_day_category[(teacher, d)] = model.NewIntVar(0, 2, f'{teacher}_day{d}_category')

    # Add constraints for each teacher
    for teacher in teacher_batch:
        # Ensure subjects get their required number of weekly slots
        for subj in teacher_subjects[teacher]:
            weekly_slots = subject_weekly_slots[subj]
            model.Add(sum(subject_assignments[(teacher, subj, d, s)]
                          for d in range(len(days)) for s in range(num_slots)) == weekly_slots)
        
        # Ensure practical sessions get consecutive slots
        for subj in teacher_subjects[teacher]:
            if subject_consecutive_slots.get(subj, False):
                practical_hours = subject_practical_hours.get(subj, 0)
                if practical_hours > 0:
                    # For each practical session start, ensure the next slot is also assigned to the same subject
                    for d in range(len(days)):
                        for s in range(num_slots-1):
                            # If this is the start of a practical session
                            model.Add(subject_assignments[(teacher, subj, d, s)] == 1).OnlyEnforceIf(practical_sessions[(teacher, subj, d, s)])
                            model.Add(subject_assignments[(teacher, subj, d, s+1)] == 1).OnlyEnforceIf(practical_sessions[(teacher, subj, d, s)])
                    
                    # Ensure we have the correct number of practical sessions (each is 2 consecutive slots)
                    model.Add(sum(practical_sessions[(teacher, subj, d, s)] 
                                 for d in range(len(days)) for s in range(num_slots-1)) == practical_hours // 2)

        # Ensure a teacher can only teach one subject per time slot
        for d in range(len(days)):
            for s in range(num_slots):
                model.Add(sum(subject_assignments[(teacher, subj, d, s)]
                              for subj in teacher_subjects[teacher]) <= 1)

        # Set up slot categories (A, B, C)
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
            
            # Apply teacher preferences if they exist
            if teacher_day_preferences and teacher in teacher_day_preferences and d in teacher_day_preferences[teacher]:
                preferred_slot_type = teacher_day_preferences[teacher][d]
                model.Add(teacher_day_category[(teacher, d)] == preferred_slot_type)

        # Additional constraints for C-type days
        for d in range(len(days) - 1):
            c_today = model.NewBoolVar(f'{teacher}_day{d}_is_C')
            model.Add(teacher_day_category[(teacher, d)] == 2).OnlyEnforceIf(c_today)
            model.Add(teacher_day_category[(teacher, d)] != 2).OnlyEnforceIf(c_today.Not())
            model.Add(teacher_day_category[(teacher, d)] != 0).OnlyEnforceIf(c_today)

        # Limit slot type occurrences per week
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
            
        # Max hours per day
        for d in range(len(days)):
            day_slots = []
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    day_slots.append(subject_assignments[(teacher, subj, d, s)])
            model.Add(sum(day_slots) <= MAX_HOURS_PER_DAY)

        # Monday/Saturday constraints
        starts_monday = model.NewBoolVar(f'{teacher}_starts_monday')
        
        for d in range(len(days)):
            day_slots = []
            for s in range(num_slots):
                for subj in teacher_subjects[teacher]:
                    day_slots.append(subject_assignments[(teacher, subj, d, s)])
            
            if d == 5:  # Saturday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(starts_monday)
            elif d == 0:  # Monday
                model.Add(sum(day_slots) == 0).OnlyEnforceIf(starts_monday.Not())

    # Set a time limit for the solver
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 120  # 2 minutes per batch
    
    # Solve the model
    status = solver.Solve(model)
    
    # Process results
    timetables = {}
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        for teacher in teacher_batch:
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
    else:
        logging.warning(f"No feasible solution found for batch. Status: {solver.StatusName(status)}")
    
    return timetables

def add_open_elective_constraints(model, subject_assignments, teachers, days, num_slots):
    """Add constraints for open elective courses"""
    logging.info("Adding constraints for open elective courses")
    
    # Identify open elective courses (courses with 'OE' in their code)
    open_electives = {}
    for teacher in teachers:
        for subj, d, s in subject_assignments:
            if 'OE' in subj:
                if subj not in open_electives:
                    open_electives[subj] = []
                open_electives[subj].append((teacher, d, s))
    
    # Ensure open electives are scheduled at the same time
    for oe_subj, occurrences in open_electives.items():
        if len(occurrences) > 1:
            first_teacher, first_day, first_slot = occurrences[0]
            for teacher, day, slot in occurrences[1:]:
                model.Add(subject_assignments[(teacher, oe_subj, day, slot)] == 
                          subject_assignments[(first_teacher, oe_subj, first_day, first_slot)])
    
    # Ensure all open electives are scheduled at same time slots if needed
    # Note: This would require additional logic if there are multiple open elective groups

def create_timetable(csv_file_path, teacher_preferences_file=None):
    start_time = time.time()
    logging.info(f"Starting timetable creation process")
    
    try:
        df = pd.read_csv(csv_file_path)
        
    except FileNotFoundError:
        logging.error(f"File not found: {csv_file_path}")
        return None
    except pd.errors.EmptyDataError:
        logging.error(f"File is empty or invalid: {csv_file_path}")
        return None
    
    # Load teacher preferences if provided
    teacher_day_preferences = {}
    if teacher_preferences_file:
        try:
            pref_df = pd.read_csv(teacher_preferences_file)
            required_pref_columns = ['Faculty', 'Day', 'PreferredSlotType']
            if all(col in pref_df.columns for col in required_pref_columns):
                for _, row in pref_df.iterrows():
                    teacher = row['Faculty']
                    day_name = row['Day']
                    slot_type_name = row['PreferredSlotType']
                    
                    # Convert day name to index
                    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
                    if day_name in days:
                        day_idx = days.index(day_name)
                        
                        # Convert slot type name to index (A=0, B=2, C=1)
                        slot_type_map = {'A': 0, 'B': 2, 'C': 1}
                        if slot_type_name in slot_type_map:
                            slot_type_idx = slot_type_map[slot_type_name]
                            
                            # Store preference
                            if teacher not in teacher_day_preferences:
                                teacher_day_preferences[teacher] = {}
                            teacher_day_preferences[teacher][day_idx] = slot_type_idx
            else:
                logging.warning(f"Missing required columns in preferences file. Required: {required_pref_columns}")
        except FileNotFoundError:
            logging.warning(f"Teacher preferences file not found: {teacher_preferences_file}")
        except pd.errors.EmptyDataError:
            logging.warning(f"Teacher preferences file is empty or invalid: {teacher_preferences_file}")
        except Exception as e:
            logging.warning(f"Error loading teacher preferences: {str(e)}")

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
    logging.info(f"Processing {len(teachers)} teachers")
    
    # Create dictionaries for hours
    subject_lecture_hours = dict(zip(df['Subject'], df['lecture_hours']))
    subject_tutorial_hours = dict(zip(df['Subject'], df['tutorial_hours']))
    subject_practical_hours = dict(zip(df['Subject'], df['practical_hours']))
    subject_credits = dict(zip(df['Subject'], df['credits']))
    
    teacher_subjects = {teacher: df[df['Faculty'] == teacher]['Subject'].unique().tolist()
                        for teacher in teachers}

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] 
    num_slots = 7

    # Calculate weekly slots needed for each subject based on lecture, tutorial, and practical hours
    subject_weekly_slots = {}
    subject_consecutive_slots = {}  # To track which subjects need consecutive slots
    
    for subj in df['Subject'].unique():
        # Get the subject data
        subj_data = df[df['Subject'] == subj].iloc[0]
        
        # Weekly slots for lectures
        lecture_slots = subj_data['lecture_hours']
        
        # Weekly slots for tutorials
        tutorial_slots = subj_data['tutorial_hours']
        
        # Weekly slots for practicals (these will need consecutive scheduling)
        practical_slots = subj_data['practical_hours']
        
        # Total weekly slots
        total_slots = lecture_slots + tutorial_slots + practical_slots
        
        subject_weekly_slots[subj] = int(total_slots)
        
        # Mark if this subject has practicals (needs consecutive slots)
        subject_consecutive_slots[subj] = practical_slots > 1

    slot_categories = {
        0: 0, 1: 0, 2: 0,  # Morning
        3: 1, 4: 1,        # Afternoon
        5: 2, 6: 2         # Evening
    }

    # Process teachers in batches for large datasets
    all_timetables = {}
    
    # Determine batch size based on number of teachers
    batch_size = min(MAX_TEACHERS_PER_BATCH, max(1, len(teachers) // 20))
    logging.info(f"Processing teachers in batches of {batch_size}")
    
    # Split teachers into batches
    teacher_batches = [teachers[i:i + batch_size] for i in range(0, len(teachers), batch_size)]
    
    # Process each batch
    for i, teacher_batch in enumerate(teacher_batches):
        logging.info(f"Processing batch {i+1}/{len(teacher_batches)} with {len(teacher_batch)} teachers")
        batch_timetables = process_teacher_batch(
            teacher_batch, df, subject_lecture_hours, subject_tutorial_hours, 
            subject_practical_hours, subject_weekly_slots, subject_consecutive_slots,
            teacher_subjects, days, num_slots, slot_categories, teacher_day_preferences
        )
        
        # Add results to overall timetables
        if batch_timetables:
            all_timetables.update(batch_timetables)
            logging.info(f"Batch {i+1} complete. Total timetables: {len(all_timetables)}/{len(teachers)}")
        else:
            logging.warning(f"Batch {i+1} failed to produce valid timetables")
    
    elapsed_time = time.time() - start_time
    logging.info(f"Timetable creation completed in {elapsed_time:.2f} seconds")
    logging.info(f"Generated timetables for {len(all_timetables)}/{len(teachers)} teachers")
    
    if all_timetables:
        return all_timetables
    else:
        logging.error("Failed to generate any valid timetables")
        return None

def export_timetable_to_csv(timetables, output_file="teacher_timetables.csv"):
    if timetables is None:
        logging.warning("No timetable data to export.")
        return None

    all_timetables = pd.concat(timetables.values(), ignore_index=True)
    
    all_timetables.to_csv(output_file, index=False)
    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file

def export_timetable_to_excel(timetables, output_file="teacher_timetables.xlsx", teacher_preferences=None):
    if timetables is None:
        logging.warning("No timetable data to export.")
        return None

    all_timetables = pd.concat(timetables.values(), ignore_index=True)
    
    with pd.ExcelWriter(output_file) as writer:
        all_timetables.to_excel(writer, sheet_name="All Teachers", index=False)

        for teacher, df in timetables.items():
            sheet_name = teacher[:31]  
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # Add a template sheet for teacher preferences if not provided
        if teacher_preferences is None:
            # Create a template for teacher preferences
            pref_template = []
            for teacher in timetables.keys():
                for day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']:
                    pref_template.append([teacher, day, ''])
            
            pref_df = pd.DataFrame(pref_template, columns=['Faculty', 'Day', 'PreferredSlotType'])
            pref_df.to_excel(writer, sheet_name="SlotTypePreferences", index=False)
            
            # Add a description of slot types
            slot_types_desc = [
                ['A', '8–3', 'Free slot between 4-6'],
                ['B', '10–5', 'Free slot between 2-4'],
                ['C', '12–7', 'Free slot between 1-2']
            ]
            slot_types_df = pd.DataFrame(slot_types_desc, columns=['SlotType', 'Hours', 'Free Slot'])
            slot_types_df.to_excel(writer, sheet_name="SlotTypeInfo", index=False)

    logging.info(f"✅ Timetable successfully exported to '{output_file}'")
    return output_file

def visualize_timetables(timetables, output_dir="timetable_visualizations"):
    """Generate visual timetables for each teacher"""
    try:
        import matplotlib.pyplot as plt
        import matplotlib as mpl
    except ImportError:
        logging.warning("Matplotlib not available. Skipping visualization.")
        return None
    
    if timetables is None:
        logging.warning("No timetable data to visualize.")
        return None
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Set color scheme
    colors = {
        'A (8–3)': '#8dd3c7',
        'B (10–5)': '#ffffb3',
        'C (12–7)': '#bebada'
    }
    
    # Process each teacher
    for teacher, df in timetables.items():
        plt.figure(figsize=(14, 8))
        plt.title(f"Weekly Timetable for {teacher}", fontsize=16)
        
        days = df['Day'].unique()
        slot_columns = [col for col in df.columns if 'Slot' in col]
        
        # Create a grid
        grid = np.empty((len(days), len(slot_columns)), dtype=object)
        grid_colors = np.empty((len(days), len(slot_columns)), dtype=object)
        
        # Fill the grid with subjects and colors
        for i, day in enumerate(days):
            day_data = df[df['Day'] == day]
            slot_type = day_data['SlotType'].iloc[0]
            
            for j, slot in enumerate(slot_columns):
                subject = day_data[slot].iloc[0]
                grid[i, j] = subject
                
                if subject:
                    # Use color based on whether it's a practical
                    if '(Practical)' in subject:
                        grid_colors[i, j] = '#fc8d62'  # Orange for practicals
                    else:
                        grid_colors[i, j] = '#66c2a5'  # Green for regular classes
                else:
                    grid_colors[i, j] = '#f7f7f7'  # Light gray for empty slots
        
        # Create table plot
        fig, ax = plt.subplots(figsize=(14, 8))
        ax.axis('tight')
        ax.axis('off')
        
        # Add day type color bars
        day_types = df['SlotType'].values
        for i, day_type in enumerate(day_types):
            ax.add_patch(plt.Rectangle((0, i), 0.5, 1, fill=True, color=colors[day_type]))
        
        # Create the table
        table = ax.table(
            cellText=grid,
            rowLabels=days,
            colLabels=slot_columns,
            cellColours=grid_colors,
            loc='center',
            cellLoc='center'
        )
        
        # Adjust table style
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)
        
        # Save plot
        file_name = os.path.join(output_dir, f"{teacher.replace(' ', '_')}_timetable.png")
        plt.savefig(file_name, dpi=150, bbox_inches='tight')
        plt.close()
    
    logging.info(f"✅ Visualizations created in '{output_dir}'")
    return output_dir

def get_survey_lab_subjects(df):
    """Identify subjects related to survey lab based on course code"""
    if SURVEY_LAB_CODE:
        survey_subjects = df[df['course_code'].str.contains(SURVEY_LAB_CODE, na=False)]['course_code'].unique().tolist()
        return survey_subjects
    return []

def analyze_timetable_quality(timetables):
    """Analyze the quality of generated timetables"""
    if not timetables:
        return None
    
    results = {
        'teacher_count': len(timetables),
        'avg_consecutive_lectures': 0,
        'avg_free_slots': 0,
        'teachers_with_ideal_schedule': 0,
        'teachers_with_back_to_