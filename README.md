# JSON Schema Extractor and Formatter

A web-based tool to extract, explore, and convert JSON files to CSV or JSON format with custom field selection and mapping. Built with Gradio for an intuitive user interface.

## Features

- 📄 **JSON File Upload**: Support for any JSON file structure
- 🌳 **Interactive Schema Explorer**: Hierarchical view of all available fields
- ✅ **Selective Field Extraction**: Choose only the fields you need
- 🏷️ **Field Mapping**: Rename output columns to your preference
- 📊 **Multiple Export Formats**: Export to CSV or JSON
- 🎯 **Root Path Selection**: Handle nested arrays and complex structures
- 🌐 **Web Interface**: Easy-to-use Gradio-powered UI

## Installation

### Prerequisites

- Python 3.7 or higher
- pip package manager

### Install Dependencies

1. Clone the repository:
```bash
git clone https://github.com/your-username/JSON-Schema-Extractor-and-Formatter.git
cd JSON-Schema-Extractor-and-Formatter
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install gradio pandas
```

## Usage

### Starting the Application

Run the application:
```bash
python app.py
```

The application will start a local web server. Open your browser and navigate to the provided URL (typically `http://127.0.0.1:7860`).

### Using the Tool

1. **Upload JSON File**
   - Click "Upload JSON File" and select your JSON file
   - The tool will automatically parse and analyze the structure

2. **Select Fields**
   - Browse the hierarchical field tree in the left panel
   - Check the boxes for fields you want to include in your output
   - Nested fields are organized in expandable accordions

3. **Configure Output**
   - Choose output format: CSV or JSON
   - Select the data root path for iteration (useful for nested arrays)
   - Map field names to custom output column names if needed

4. **Export Data**
   - Enter an optional output filename
   - Click "Export Data" to generate the file
   - Download the result from the provided link

### Example Use Cases

- **API Response Processing**: Extract specific fields from complex API responses
- **Data Migration**: Convert JSON data to CSV for spreadsheet analysis
- **Log Analysis**: Parse and flatten structured log files
- **Database Import**: Prepare JSON data for database insertion
- **Reporting**: Extract relevant metrics from nested JSON structures

### Supported JSON Structures

- Simple objects: `{"name": "John", "age": 30}`
- Nested objects: `{"user": {"profile": {"name": "John"}}}`
- Arrays of objects: `[{"id": 1, "name": "Item1"}, {"id": 2, "name": "Item2"}]`
- Mixed structures with arrays and nested objects

## Project Structure

```
JSON-Schema-Extractor-and-Formatter/
├── app.py              # Main application file
├── requirements.txt    # Python dependencies
├── README.md          # This file
└── updated_dataset.json # Sample data file
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and commit: `git commit -am 'Add feature'`
4. Push to the branch: `git push origin feature-name`
5. Submit a pull request

## License

This project is open source. Please check the LICENSE file for details.
