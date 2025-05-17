# Import the correct functions from usingMLIP.py
from usingMLIP import create_milp_timetable, export_timetable_to_excel

def main():
    # Define the input CSV file path
    input_file = "filtered_file1.csv"
    
    # Print progress message
    print(f"Generating timetable from {input_file}...")
    
    # Call the function to create the timetable (make sure the function name matches)
    timetables = create_milp_timetable(input_file)
    
    # If timetable creation is successful, export it
    if timetables:
    
        
        # Export to Excel
        excel_file = export_timetable_to_excel(timetables, "teacher_timetables-4.xlsx")
        
        # Print success message with output file paths
        print("\nTimetable generation completed successfully!")
        print(f"Excel output: {excel_file}")
    else:
        # If timetable creation fails, print an error message
        print("\nFailed to generate timetable. Please check your input data.")

# Ensure the script runs when executed directly
if __name__ == "__main__":
    main()
