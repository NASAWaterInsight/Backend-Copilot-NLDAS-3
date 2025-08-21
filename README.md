# NLDAS-3 Copilot

AI-powered copilot for accessing and analyzing NLDAS-3 (North American Land Data Assimilation System) forcing data through Azure Functions and AI Agents.

## Overview

This project provides an intelligent interface to query NLDAS-3 meteorological data including precipitation, temperature, wind, humidity, and radiation parameters. The system integrates Azure Functions with AI Agents to deliver natural language access to hydrology and water resources data.

## Features

- **Meteorological Data Access**: Query precipitation, temperature, wind, and other NLDAS-3 parameters
- **Location-based Queries**: Get data for specific geographic locations  
- **Time Range Support**: Access monthly, daily, and hourly data
- **AI Agent Integration**: Natural language queries through Azure AI
- **Blob Storage Backend**: Efficient data storage and retrieval
- **AI Search Integration**: Enhanced data discovery and embedding

## Architecture

- **Azure Functions**: HTTP and queue-triggered functions for data processing
- **Azure AI Agents**: Natural language interface for data queries
- **Azure Blob Storage**: NLDAS-3 data storage with monthly images
- **Azure AI Search**: Data indexing and embedding for efficient retrieval

## API Endpoints

### HTTP Trigger (for testing)
```
GET /api/nldas3?parameter=precipitation&location=Maryland&date_range=2024-01
POST /api/nldas3
```

### Queue Trigger (for AI Agent integration)
- Input Queue: `azure-function-foo-input`
- Output Queue: `azure-function-foo-output`

## Sample Request/Response

**Request:**
```json
{
  "parameter": "precipitation",
  "location": "Maryland",
  "date_range": "2024-01"
}
```

**Response:**
```json
{
  "parameter": "precipitation",
  "location": "Maryland",
  "date_range": "2024-01",
  "result": "NLDAS-3 precipitation data for Maryland (2024-01): Average 45mm/month",
  "status": "success",
  "data_source": "NLDAS-3 blob storage with AI search integration"
}
```

## Development

### Prerequisites
- Python 3.8+
- Azure Functions Core Tools
- Azure subscription with AI Services

### Local Development
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure `local.settings.json` with your Azure credentials
4. Run locally: `func start`
5. Test with tools like Insomnia or Postman

### Environment Variables
- `STORAGE_CONNECTION`: Azure Storage connection string
- `PROJECT_ENDPOINT`: Azure AI Project endpoint
- `MODEL_DEPLOYMENT_NAME`: AI model deployment name

## Related Projects

Part of the NASA Water Insight initiative for advancing hydrological data accessibility and analysis.

## License

[Add your license information]

## Contact

[Add contact information]
