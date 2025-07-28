# PyNominate W-NOMINATE API Integration

Streamlined integration for React → Golang API → Python → MongoDB workflow.

## Architecture Overview

**Complete Flow:**
1. **React Frontend** → User searches/filters votations by labels, dates, etc.
2. **React Frontend** → User selects specific votations for analysis
3. **React Frontend** → Sends list of votation IDs to Golang API
4. **Golang API** → Validates request and calls Python module with votation IDs
5. **Python Module** → Connects to MongoDB, fetches data, calculates W-NOMINATE
6. **Python Module** → Returns political map results to Golang API
7. **Golang API** → Returns results to React
8. **React Frontend** → Visualizes political map for user interaction

## Key Components

### 1. `wnominate_api.py` - Main API Module
- **WNominateCalculator**: Main class handling the complete workflow
- **Environment Detection**: Automatically detects localhost vs production
- **MongoDB Integration**: Fetches votation and member data
- **W-NOMINATE Calculation**: Processes data through nominate algorithm
- **Response Formatting**: Returns structured data ready for React visualization

### 2. `nominate_cli.py` - Command Line Interface
- Simple CLI for Golang to call via subprocess
- Takes votation IDs as JSON array
- Returns political map results as JSON

## Environment Configuration

The module automatically detects whether it's running on localhost or production:

### Environment Variables
```bash
# Development (localhost)
MONGO_URI_DEV=mongodb://localhost:27017/
NODE_ENV=development
ENVIRONMENT=dev
IS_LOCAL=true

# Production
MONGO_URI_PROD=mongodb://your-prod-server:27017/
NODE_ENV=production
ENVIRONMENT=prod
```

## Usage

### From Golang API

```go
package main

import (
    "encoding/json"
    "os/exec"
    "bytes"
)

func CalculateWNominate(votationIDs []int) (map[string]interface{}, error) {
    // Convert votation IDs to JSON
    idsJSON, err := json.Marshal(votationIDs)
    if err != nil {
        return nil, err
    }
    
    // Call Python CLI
    cmd := exec.Command("python3", "nominate_cli.py", 
                       "--votation-ids", string(idsJSON), 
                       "--pretty")
    
    var out bytes.Buffer
    var errOut bytes.Buffer
    cmd.Stdout = &out
    cmd.Stderr = &errOut
    
    err = cmd.Run()
    if err != nil {
        return nil, fmt.Errorf("Python execution failed: %s", errOut.String())
    }
    
    // Parse result
    var result map[string]interface{}
    err = json.Unmarshal(out.Bytes(), &result)
    return result, err
}

// Example API endpoint
func handleWNominateCalculation(w http.ResponseWriter, r *http.Request) {
    var request struct {
        VotationIDs []int `json:"votation_ids"`
    }
    
    if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
        http.Error(w, "Invalid request", http.StatusBadRequest)
        return
    }
    
    // Validate votation IDs (optional - can be done in Python too)
    if len(request.VotationIDs) == 0 {
        http.Error(w, "No votation IDs provided", http.StatusBadRequest)
        return
    }
    
    result, err := CalculateWNominate(request.VotationIDs)
    if err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }
    
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(result)
}
```

### Direct Python Usage

```python
from wnominate_api import calculate_wnominate_from_ids

# Calculate from votation IDs
votation_ids = [37270, 37269, 37268]
result = calculate_wnominate_from_ids(votation_ids)

if result['success']:
    # Access political map data
    members = result['political_map']['members']
    votations = result['political_map']['votations']
    
    # Each member has coordinates for plotting
    for member in members:
        print(f"{member['name']}: x={member['coordinates']['x']}, y={member['coordinates']['y']}")
```

### CLI Usage

```bash
# Basic usage
python nominate_cli.py --votation-ids "[37270,37269,37268]"

# With custom parameters
python nominate_cli.py --votation-ids "[37270,37269,37268]" --maxiter 50 --cores 2 --pretty

# Save to file
python nominate_cli.py --votation-ids "[37270,37269,37268]" --output results.json --pretty
```

## Input/Output Format

### Input (from React via Golang)
```json
{
    "votation_ids": [37270, 37269, 37268]
}
```

### Output (to React via Golang)
```json
{
    "success": true,
    "timestamp": "2023-01-15T10:30:00",
    "environment": "localhost",
    "calculation_summary": {
        "num_votations": 3,
        "num_members": 155,
        "iterations_completed": 25,
        "calculation_time_minutes": 1.23,
        "votation_ids_processed": [37270, 37269, 37268]
    },
    "political_map": {
        "members": [
            {
                "id": 1000,
                "name": "Juan Pérez",
                "party": "Partido Conservador",
                "coordinates": {
                    "x": 0.45,
                    "y": -0.12
                },
                "region": "Norte",
                "metadata": {...}
            }
        ],
        "votations": [
            {
                "id": 37270,
                "title": "Reforma de Salud",
                "date": "2023-01-15",
                "parameters": {
                    "yea_coordinates": [0.2, 0.1],
                    "nay_coordinates": [-0.2, -0.1],
                    "log_likelihood": -45.67
                }
            }
        ],
        "dimensions": 2,
        "algorithm_parameters": {
            "w": 0.4619,
            "b": 8.8633
        }
    },
    "statistics": {
        "overall_log_likelihood": -234.56,
        "geometric_mean_probability": 0.8234
    }
}
```

## React Frontend Integration

```javascript
// Example React component for W-NOMINATE calculation
const WNominateCalculator = () => {
    const [selectedVotations, setSelectedVotations] = useState([]);
    const [politicalMap, setPoliticalMap] = useState(null);
    const [isCalculating, setIsCalculating] = useState(false);

    const calculatePoliticalMap = async () => {
        setIsCalculating(true);
        
        try {
            const response = await fetch('/api/wnominate/calculate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    votation_ids: selectedVotations.map(v => v.id)
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                setPoliticalMap(result.political_map);
                // Now render the political map visualization
            } else {
                console.error('Calculation failed:', result.error);
            }
        } catch (error) {
            console.error('API call failed:', error);
        } finally {
            setIsCalculating(false);
        }
    };

    return (
        <div>
            <VotationSelector 
                onSelectionChange={setSelectedVotations}
                selectedVotations={selectedVotations}
            />
            
            <button 
                onClick={calculatePoliticalMap}
                disabled={selectedVotations.length === 0 || isCalculating}
            >
                {isCalculating ? 'Calculating...' : `Calculate Map (${selectedVotations.length} votations)`}
            </button>
            
            {politicalMap && (
                <PoliticalMapVisualization 
                    members={politicalMap.members}
                    votations={politicalMap.votations}
                />
            )}
        </div>
    );
};
```

## Database Schema

The module expects these MongoDB collections in the `quevotanEtiquetado` database:

- **votaciones**: Votation metadata (`id`, `fecha`, `titulo`)
- **VotosDiputados**: Voting details (`id`, `detalle` with member votes)
- **parlamentarios**: Member information (`id`, `nombre`, `partido`, `region`)

## Error Handling

The API provides comprehensive error handling:

```json
{
    "success": false,
    "timestamp": "2023-01-15T10:30:00",
    "environment": "localhost",
    "error": "No valid votations found for provided IDs",
    "debug_info": "..." // Only included in localhost environment
}
```

## Production Deployment

### Environment Setup
1. Set production environment variables
2. Ensure MongoDB connection is accessible
3. Install Python dependencies: `pip install -r requirements.txt`
4. Test with sample votation IDs

### Performance Considerations
- Use `cores: 1` for API calls to avoid resource conflicts
- Consider caching results for frequently requested votation sets
- Monitor memory usage with large votation sets
- Set reasonable `maxiter` limits (30-50) for API responsiveness

## Testing

Test the complete flow:

```bash
# Test with sample votation IDs
python nominate_cli.py --votation-ids "[37270,37269,37268]" --pretty

# Test environment detection
python -c "from wnominate_api import WNominateCalculator; c = WNominateCalculator(); print(f'Environment: {c._is_localhost()}')"
```

The module is now perfectly aligned with your React → Golang → Python → MongoDB architecture!

## Quick Start

### Primary Use Case: React → Golang → Python

The recommended flow for your architecture:

```python
from api_wrapper import main_api_endpoint

# Data structure that React would send to Golang API
# (after React has already fetched and filtered votations)
request_data = {
    'votations': [
        {
            "id": 37270,
            "fecha": "2023-01-15",
            "titulo": "Healthcare Reform Bill",
            "detalle": {
                "1000": 1,  # Member ID: Vote (1=Yes, 0=No, 2=Abstain)
                "1001": 0,
                "1002": 1,
                # ... all members who participated
            }
        },
        {
            "id": 37269,
            "fecha": "2023-01-16", 
            "titulo": "Budget Approval",
            "detalle": {
                "1000": 0,
                "1001": 1,
                "1002": 2,
                # ... member votes
            }
        }
        # ... more votations selected by user in React
    ],
    'members': [
        {"id": 1000, "nombre": "Juan Pérez", "partido": "Partido A"},
        {"id": 1001, "nombre": "María García", "partido": "Partido B"},
        {"id": 1002, "nombre": "Carlos López", "partido": "Partido A"},
        # ... all members (fetched by React)
    ],
    'config': {
        'maxiter': 30,
        'cores': 1,
        'xtol': 1e-4
    }
}

# Process the data (this happens in your Golang API)
result = main_api_endpoint(request_data)
```

### Alternative: Using the CLI Tool from Golang

```bash
# Your Golang API can call this directly
python nominate_cli.py -i selected_votations.json -o nominate_results.json --pretty
```

## Input Data Format (Pre-fetched by React)

### Votations Data
```json
[
  {
    "id": 37270,
    "fecha": "2023-01-15",
    "titulo": "Healthcare Reform Bill",
    "etiquetas": ["healthcare", "social-policy"],
    "detalle": {
      "1000": 1,  // Member 1000 voted Yes
      "1001": 0,  // Member 1001 voted No
      "1002": 2,  // Member 1002 abstained
      "1003": 1   // Member 1003 voted Yes
    }
  },
  {
    "id": 37269, 
    "fecha": "2023-01-16",
    "titulo": "Budget Approval 2023",
    "etiquetas": ["budget", "economy"],
    "detalle": {
      "1000": 0,  // Member votes for this votation
      "1001": 1,
      "1002": 2,
      "1003": 0
    }
  }
]
```

### Members Data  
```json
[
  {
    "id": 1000,
    "nombre": "Juan Pérez",
    "partido": "Partido Conservador",
    "region": "Norte"
  },
  {
    "id": 1001,
    "nombre": "María García", 
    "partido": "Partido Liberal",
    "region": "Centro"
  }
]
```

### Configuration Options
```json
{
  "maxiter": 30,        // Maximum iterations for convergence
  "cores": 1,           // Number of CPU cores (recommend 1 for API calls)
  "xtol": 0.0001,      // Convergence tolerance
  "update": ["bp", "idpt", "bw"],  // What parameters to update
  "add_meta": ["members"]  // Include member metadata in results
}
```

## Output Format

```json
{
  "success": true,
  "timestamp": "2023-01-15T10:30:00",
  "input_summary": {
    "num_votations": 3,
    "num_members": 150,
    "votation_ids": ["V37270", "V37269", "V37268"]
  },
  "results": {
    "ideal_points": {
      "M1000": {
        "coordinates": [0.45, -0.12],
        "metadata": {...}
      }
    },
    "bill_parameters": {
      "V37270": {
        "parameters": [0.1, 0.2, 0.05, 0.1],
        "log_likelihood": -123.45
      }
    },
    "weights": {
      "w": 0.4619,
      "b": 8.8633
    },
    "control": {
      "iterations": 25,
      "time": 1.23,
      "cores": 1
    }
  }
}
```

## Golang Integration Example

This is how your Golang API would integrate with the Python module:

```go
package main

import (
    "encoding/json"
    "os/exec"
    "bytes"
    "io/ioutil"
    "fmt"
    "os"
)

type NominateRequest struct {
    Votations []map[string]interface{} `json:"votations"`
    Members   []map[string]interface{} `json:"members"`
    Config    map[string]interface{}   `json:"config,omitempty"`
}

type NominateResponse struct {
    Success      bool                   `json:"success"`
    Timestamp    string                 `json:"timestamp"`
    InputSummary map[string]interface{} `json:"input_summary,omitempty"`
    Results      map[string]interface{} `json:"results,omitempty"`
    Error        string                 `json:"error,omitempty"`
}

// ProcessNominate handles the W-NOMINATE calculation
// Called after React has fetched and selected the votations
func ProcessNominate(data NominateRequest) (*NominateResponse, error) {
    // Convert request to JSON
    jsonData, err := json.Marshal(data)
    if err != nil {
        return nil, fmt.Errorf("failed to marshal request: %v", err)
    }
    
    // Create temporary input file
    tempFile := fmt.Sprintf("/tmp/nominate_input_%d.json", time.Now().Unix())
    err = ioutil.WriteFile(tempFile, jsonData, 0644)
    if err != nil {
        return nil, fmt.Errorf("failed to write temp file: %v", err)
    }
    defer os.Remove(tempFile)
    
    // Execute Python CLI
    cmd := exec.Command("python3", "nominate_cli.py", "-i", tempFile)
    var out bytes.Buffer
    var errOut bytes.Buffer
    cmd.Stdout = &out
    cmd.Stderr = &errOut
    
    err = cmd.Run()
    if err != nil {
        return &NominateResponse{
            Success: false,
            Error:   fmt.Sprintf("Python execution failed: %s", errOut.String()),
        }, nil
    }
    
    // Parse the result
    var result NominateResponse
    err = json.Unmarshal(out.Bytes(), &result)
    if err != nil {
        return nil, fmt.Errorf("failed to parse result: %v", err)
    }
    
    return &result, nil
}

// HTTP handler example for your API endpoint
func handleNominateCalculation(w http.ResponseWriter, r *http.Request) {
    var req NominateRequest
    
    // Decode the request from React
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, "Invalid request body", http.StatusBadRequest)
        return
    }
    
    // Validate that votations and members are provided
    if len(req.Votations) == 0 {
        http.Error(w, "No votations provided", http.StatusBadRequest)
        return
    }
    
    if len(req.Members) == 0 {
        http.Error(w, "No members provided", http.StatusBadRequest)
        return
    }
    
    // Process with Python module
    result, err := ProcessNominate(req)
    if err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }
    
    // Return results to React
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(result)
}
```

## React Frontend Integration Flow

### 1. User Searches and Filters Votations in React

```javascript
// Example React component for votation selection
const VotationSelector = () => {
  const [votations, setVotations] = useState([]);
  const [selectedVotations, setSelectedVotations] = useState([]);
  const [filters, setFilters] = useState({
    dateRange: { start: '', end: '' },
    labels: [],
    searchText: ''
  });

  // Fetch votations based on filters
  const searchVotations = async () => {
    const response = await fetch('/api/votations/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(filters)
    });
    const results = await response.json();
    setVotations(results.votations);
  };

  // Send selected votations for W-NOMINATE calculation
  const calculateNominate = async () => {
    const payload = {
      votations: selectedVotations,
      members: await fetchAllMembers(),
      config: {
        maxiter: 30,
        cores: 1,
        add_meta: ['members']
      }
    };

    const response = await fetch('/api/nominate/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const results = await response.json();
    
    if (results.success) {
      // Display the political map with ideal points
      displayPoliticalMap(results.results);
    } else {
      console.error('Calculation failed:', results.error);
    }
  };

  return (
    <div>
      {/* Search filters UI */}
      <VotationFilters filters={filters} onChange={setFilters} />
      <button onClick={searchVotations}>Search Votations</button>
      
      {/* Votation selection UI */}
      <VotationList 
        votations={votations}
        selected={selectedVotations}
        onSelectionChange={setSelectedVotations}
      />
      
      {/* Calculate button */}
      <button 
        onClick={calculateNominate}
        disabled={selectedVotations.length === 0}
      >
        Calculate Political Map ({selectedVotations.length} votations)
      </button>
    </div>
  );
};
```

### 2. Expected API Endpoints in Your Golang Backend

```go
// GET/POST /api/votations/search
// - Handles filtering by date, labels, search text
// - Returns matching votations with voting details

// POST /api/nominate/calculate  
// - Receives selected votations + members data from React
// - Calls Python module via CLI
// - Returns W-NOMINATE results for map visualization
```

## Testing

Run the test suite to verify functionality:

```bash
python test_api_wrapper.py
```

This will:
- Test full votation processing
- Test selective votation processing  
- Test error handling
- Generate sample input files
- Show Golang integration examples

## Configuration for Production

### Environment Variables
- `MONGO_URI`: MongoDB connection string
- `NOMINATE_CORES`: Number of CPU cores to use
- `NOMINATE_MAX_ITER`: Maximum iterations

### Performance Considerations
- Use multiple cores for large datasets
- Consider limiting the number of votations processed simultaneously
- Monitor memory usage with large member sets

## Error Handling

The API provides structured error responses:

```json
{
  "success": false,
  "timestamp": "2023-01-15T10:30:00",
  "error": "Error description",
  "traceback": "..." // Only in debug mode
}
```

Common errors:
- No votations data provided
- No members data provided  
- Invalid votation IDs
- MongoDB connection issues
- Insufficient data for convergence

## Integration Checklist

✅ **Ready for Integration:**
- Clean API interface with structured input/output
- Command-line interface perfect for microservice calls
- No database dependencies (React handles data fetching)
- Comprehensive error handling and validation
- Configurable parameters for different use cases
- Test suite with realistic examples

✅ **Perfect for React → Golang → Python Flow:**
- React fetches and filters votations via existing API
- React allows user selection of specific votations
- Golang receives selected data and calls Python module
- Python processes only the selected votations
- Results flow back through Golang to React for visualization

✅ **Production Ready Features:**
- Input validation for all data structures
- Structured JSON responses with detailed metadata
- Performance configuration (iterations, cores, tolerance)
- Comprehensive error handling with descriptive messages
- Sample integration code for Golang and React

## Recommended Implementation Steps

1. **Test the Python module** with your existing data:
   ```bash
   python test_api_wrapper.py
   ```

2. **Create sample integration** in Golang:
   - Test the CLI interface with sample data
   - Validate JSON input/output formats
   
3. **Implement React UI** for votation selection:
   - Search/filter interface using existing API
   - Multi-select votation list
   - Configuration options for calculation
   
4. **Add Golang endpoint** that bridges React and Python:
   - Validate incoming data from React
   - Call Python CLI with proper error handling
   - Return formatted results to React

5. **Build visualization** in React:
   - Parse ideal points coordinates  
   - Display interactive political map
   - Show member positions and bill parameters

The module is now optimally prepared for your React → Golang → Python architecture!
