import pandas as pd
import pulp
import logging
from collections import defaultdict

HOURS_PER_CREDIT = 18
WEEKS_IN_SEMESTER = 18
MAX_HOURS_PER_DAY = 5
NUM_DAYS = 6
NUM_SLOTS = 7
MORNING_SLOTS = [0, 1, 2]
AFTERNOON_SLOTS = [3, 4]
EVENING_SLOTS = [5, 6]
DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
SLOT_CATEGORIES = {s: 0 for s in MORNING_SLOTS} | {s: 1 for s in AFTERNOON_SLOTS} | {s: 2 for s in EVENING_SLOTS}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def create_milp_timetable(csv_file_path):
    try:
        df = pd.read_csv(csv_file_path)
    except Exception as e:
        logging.error(f"CSV read error: {e}")
        return None

    df['Credits'] = pd.to_numeric(df['Credits'], errors='coerce')
    df = df.dropna(subset=['Credits'])
    df = df[(df['Credits'] >= 1) & (df['Credits'] <= 5)]

    df['Subject'] = df['Code']
    teachers = sorted(df['Faculty'].dropna().unique().tolist())
    subject_credits = dict(zip(df['Subject'], df['Credits']))
    teacher_subjects = {teacher: df[df['Faculty'] == teacher]['Subject'].unique().tolist() for teacher in teachers}

    subject_weekly_slots = {
        subj: max(1, round((credits * HOURS_PER_CREDIT) / WEEKS_IN_SEMESTER))
        for subj, credits in subject_credits.items()
    }

    model = pulp.LpProblem("TimetableScheduling", pulp.LpMinimize)

    x = pulp.LpVariable.dicts("Assign", ((t, s, d, sl) for t in teachers for s in teacher_subjects[t] for d in range(NUM_DAYS) for sl in range(NUM_SLOTS)), cat='Binary')
    slot_type = pulp.LpVariable.dicts("SlotType", ((t, d, stype) for t in teachers for d in range(NUM_DAYS) for stype in range(3)), cat='Binary')
    works_mon_to_fri = pulp.LpVariable.dicts("WorkWeek", (t for t in teachers), cat='Binary')

    # Objective: no minimization needed; dummy zero
    model += 0

    # Weekly slot count
    for t in teachers:
        for s in teacher_subjects[t]:
            model += pulp.lpSum(x[t, s, d, sl] for d in range(NUM_DAYS) for sl in range(NUM_SLOTS)) == subject_weekly_slots[s]

    # No more than 1 subject per slot
    for t in teachers:
        for d in range(NUM_DAYS):
            for sl in range(NUM_SLOTS):
                model += pulp.lpSum(x[t, s, d, sl] for s in teacher_subjects[t]) <= 1

    # Max hours per day
    for t in teachers:
        for d in range(NUM_DAYS):
            model += pulp.lpSum(x[t, s, d, sl] for s in teacher_subjects[t] for sl in range(NUM_SLOTS)) <= MAX_HOURS_PER_DAY
    
    

    # One slot type per day
    for t in teachers:
        for d in range(NUM_DAYS):
            for stype in range(3):
                slots = [sl for sl in range(NUM_SLOTS) if SLOT_CATEGORIES[sl] == stype]
                model += pulp.lpSum(x[t, s, d, sl] for s in teacher_subjects[t] for sl in slots) >= slot_type[t, d, stype]  # Activate if used
            model += pulp.lpSum(slot_type[t, d, stype] for stype in range(3)) <= 1  # Only one type

    # Slot type transition: if Evening today, no Morning next day
    for t in teachers:
        for d in range(NUM_DAYS - 1):
            model += slot_type[t, d, 2] + slot_type[t, d + 1, 0] <= 1

    # Work week constraint
    for t in teachers:
        for d in range(NUM_DAYS):
            is_monday = (d == 0)
            is_saturday = (d == 5)
            for sl in range(NUM_SLOTS):
                for s in teacher_subjects[t]:
                    # Monday must be free if Tue–Sat
                    if is_monday:
                        model += x[t, s, d, sl] <= works_mon_to_fri[t]
                    # Saturday must be free if Mon–Fri
                    if is_saturday:
                        model += x[t, s, d, sl] <= 1 - works_mon_to_fri[t]

    # Solve
    status = model.solve()
    if status != pulp.LpStatusOptimal:
        logging.error("❌ No feasible timetable found.")
        return None

    # Build timetable
    timetable = defaultdict(list)
    for t in teachers:
        for d in range(NUM_DAYS):
            row = [t, DAYS[d]]
            for sl in range(NUM_SLOTS):
                subject = ''
                for s in teacher_subjects[t]:
                    if pulp.value(x[t, s, d, sl]) == 1:
                        subject = s
                        break
                row.append(subject)
            type_used = next((stype for stype in range(3) if pulp.value(slot_type[t, d, stype]) == 1), -1)
            row.append(['A (8–3)', 'B (10–5)', 'C (12–7)'][type_used] if type_used >= 0 else '')
            timetable[t].append(row)

    # Convert to DataFrames
    final_tables = {t: pd.DataFrame(rows, columns=['Teacher', 'Day'] + [f'Slot {i+1}' for i in range(NUM_SLOTS)] + ['SlotType']) for t, rows in timetable.items()}
    logging.info("✅ MILP Timetable generated successfully.")
    return final_tables

def export_timetable_to_excel(timetables, output_file="timetable_output.xlsx"):
    if not timetables:
        logging.warning("Nothing to export.")
        return None

    with pd.ExcelWriter(output_file) as writer:
        for teacher, df in timetables.items():
            df.to_excel(writer, sheet_name=teacher[:31], index=False)
        pd.concat(timetables.values()).to_excel(writer, sheet_name="All Teachers", index=False)

    logging.info(f"✅ Exported to {output_file}")
    return output_file
