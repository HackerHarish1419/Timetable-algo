import os
import logging
import argparse
from timetable_manager import create_timetable, export_timetable_to_csv, export_timetable_to_excel

def main():
    parser = argparse.ArgumentParser(description='University Timetable Generator')
    parser.add_argument('--input', '-i', default='course_mapping_output.csv', 
                        help='Input CSV file with course data')
    parser.add_argument('--output', '-o', default='teacher_timetables.xlsx',
                        help='Output file for timetable (Excel or CSV)')
    parser.add_argument('--format', '-f', choices=['excel', 'csv'], default='excel',
                        help='Output format (excel or csv)')
    parser.add_argument('--relaxed', '-r', action='store_true',
                        help='Relax constraints if no feasible solution is found')
    
    args = parser.parse_args()
    
    print(f"Generating timetable from {args.input}...")
    
    # First try with full constraints
    timetables = create_timetable(args.input, relaxed_constraints=False)
    
    # If that fails and relaxed mode is enabled, try with relaxed constraints
    if timetables is None and args.relaxed:
        print("No feasible solution with full constraints. Trying with relaxed constraints...")
        timetables = create_timetable(args.input, relaxed_constraints=True)
    
    if timetables is not None:
        if args.format == 'excel':
            output_file = args.output if args.output.endswith('.xlsx') else args.output + '.xlsx'
            export_timetable_to_excel(timetables, output_file)
            print(f"Timetable exported to {output_file}")
        else:  # csv
            output_file = args.output if args.output.endswith('.csv') else args.output + '.csv'
            export_timetable_to_csv(timetables, output_file)
            print(f"Timetable exported to {output_file}")
    else:
        print("Failed to generate timetable. Please check your input data")

if __name__ == "__main__":
    main()
