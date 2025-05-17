import argparse
import logging
from timetable_core import create_timetable, export_timetable_to_csv, export_timetable_to_excel

def main():
    parser = argparse.ArgumentParser(description='Create a timetable based on a CSV file')
    parser.add_argument('csv_file', help='Path to the CSV file containing course data')
    parser.add_argument('--output', '-o', default='teacher_timetables.xlsx', 
                        help='Output file path (default: teacher_timetables.xlsx)')
    parser.add_argument('--format', '-f', choices=['csv', 'excel'], default='excel',
                        help='Output format: csv or excel (default: excel)')
    
    args = parser.parse_args()
    
    timetables = create_timetable(args.csv_file)
    
    if timetables:
        if args.format == 'csv':
            export_timetable_to_csv(timetables, args.output)
        else:
            export_timetable_to_excel(timetables, args.output)
        
        logging.info(f"Timetable creation complete! Output saved to {args.output}")
    else:
        logging.error("Failed to create timetable.")
        return 1
    
    return 0

if __name__ == "__main__":
    main()