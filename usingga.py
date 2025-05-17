import random
import pandas as pd
import logging
import numpy as np

# Constants
HOURS_PER_CREDIT = 18
WEEKS_IN_SEMESTER = 18
MAX_HOURS_PER_DAY = 5
MORNING_SLOTS = [0, 1, 2]  # Slots representing morning hours
SURVEY_LAB_CODE = 'CE23331'  # Survey Lab course code

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Genetic Algorithm Parameters
POPULATION_SIZE = 100
MUTATION_RATE = 0.1
CROSSOVER_RATE = 0.8
MAX_GENERATIONS = 1000
TOURNAMENT_SIZE = 5
ELITISM = True


def create_timetable(csv_file_path):
    try:
        # Read the CSV file
        df = pd.read_csv(csv_file_path)
        
        # Calculate MAX_SAME_OFF_DAY based on unique faculty count
        MAX_SAME_OFF_DAY = len(df['Faculty'].unique()) // 2
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

    # Prepare data for scheduling
    return df, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots


def generate_initial_population(df, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots):
    population = []
    for _ in range(POPULATION_SIZE):
        timetable = {}
        for teacher in teachers:
            timetable[teacher] = [random.choice(subject_credits.keys()) for _ in range(len(days) * num_slots)]
        population.append(timetable)
    return population


def fitness(timetable, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots):
    score = 0

    # Calculate the fitness based on various constraints
    for teacher in teachers:
        subject_count = {subj: 0 for subj in subject_credits.keys()}
        total_working_hours = 0
        for i, day in enumerate(days):
            for j, slot in enumerate(range(num_slots)):
                subj = timetable[teacher][i * num_slots + j]
                if subj in subject_credits:
                    subject_count[subj] += 1
                    total_working_hours += subject_credits[subj]

        # Ensure each subject is assigned the correct number of weekly slots
        for subj, count in subject_count.items():
            if count != subject_weekly_slots[subj]:
                score -= abs(count - subject_weekly_slots[subj])

        # Max working hours per day
        if total_working_hours > MAX_HOURS_PER_DAY * len(days):
            score -= 1000

    # Return the negative score for minimization
    return -score


def selection(population, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots):
    tournament = random.sample(population, TOURNAMENT_SIZE)
    scores = [fitness(ind, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots) for ind in tournament]
    winner = tournament[scores.index(max(scores))]
    return winner


def crossover(parent1, parent2, teachers, days, num_slots):
    child = {}
    for teacher in teachers:
        crossover_point = random.randint(0, len(parent1[teacher]) - 1)
        child[teacher] = parent1[teacher][:crossover_point] + parent2[teacher][crossover_point:]
    return child


def mutate(timetable, teachers, subject_credits):
    for teacher in teachers:
        if random.random() < MUTATION_RATE:
            slot_to_mutate = random.randint(0, len(timetable[teacher]) - 1)
            new_subject = random.choice(list(subject_credits.keys()))
            timetable[teacher][slot_to_mutate] = new_subject
    return timetable


def genetic_algorithm(csv_file_path):
    df, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots = create_timetable(csv_file_path)

    # Generate initial population
    population = generate_initial_population(df, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots)

    # Run the genetic algorithm
    for generation in range(MAX_GENERATIONS):
        new_population = []

        # Elitism: Preserve the best individual
        if ELITISM:
            best_individual = max(population, key=lambda ind: fitness(ind, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots))
            new_population.append(best_individual)

        # Generate new individuals through selection, crossover, and mutation
        while len(new_population) < POPULATION_SIZE:
            parent1 = selection(population, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots)
            parent2 = selection(population, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots)

            child = crossover(parent1, parent2, teachers, days, num_slots)
            child = mutate(child, teachers, subject_credits)
            new_population.append(child)

        population = new_population

        # Log progress
        best_fitness = max(fitness(ind, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots) for ind in population)
        logging.info(f"Generation {generation + 1}: Best fitness = {best_fitness}")

    # Return the best solution found
    best_solution = max(population, key=lambda ind: fitness(ind, teachers, subject_credits, teacher_subjects, subject_weekly_slots, days, num_slots))
    return best_solution


# Example Usage
csv_file_path = 'course_schedule.csv'  # Path to your CSV file
best_timetable = genetic_algorithm(csv_file_path)
