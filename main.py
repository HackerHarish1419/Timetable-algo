
from withslot import create_timetable, export_timetable_to_csv, export_timetable_to_excel

def main():
 
    input_file = "merge.csv"
    print(f"Generating timetable from {input_file}...")
    timetables = create_timetable(input_file)
    
    if timetables:
        
        csv_file = export_timetable_to_csv(timetables, "teacher_timetables-AIML_17.csv")
        
        
        excel_file = export_timetable_to_excel(timetables, "teacher_timetables-AIML_17.xlsx")
        
        print("\nTimetable generation completed successfully!")
        print(f"CSV output: {csv_file}")
        print(f"Excel output: {excel_file}")
    else:
        print("\nFailed to generate timetable. Please check your input data.")

if __name__ == "__main__":
    main()