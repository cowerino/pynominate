#!/usr/bin/env python
"""
W-NOMINATE API Module

This module consolidates the functionality of the test_update_nominate.py and generar_payload.py files,
providing a single interface for generating W-NOMINATE calculations based on a list of votation IDs.
It connects directly to MongoDB, fetches the required data, generates the payload in memory,
and runs the W-NOMINATE calculation.

This module is designed to be called from a Golang API in a Dockerized environment.
"""

import os
import sys
import json
import argparse
import hashlib
import datetime
import numpy as np
import pymongo
from typing import List, Dict, Any, Optional, Union

# Ensure pynominate is in the path
sys.path.append('.')
from pynominate.nominate import update_nominate


def get_mongodb_connection() -> pymongo.MongoClient:
    """
    Connect to MongoDB, handling both development and production environments.
    In development, connects to localhost.
    In production (Docker), connects to the MongoDB container.
    
    Returns:
        pymongo.MongoClient: A MongoDB client instance
    """
    # Check for environment variable (can be set in Docker)
    mongo_url = os.environ.get('MONGODB_URL', 'mongodb://localhost:27017/')
    
    # For Docker environment, use the service name if available
    if os.environ.get('DOCKER_ENV') == 'true':
        mongo_url = os.environ.get('MONGODB_URL', 'mongodb://mongo:27017/')
    
    return pymongo.MongoClient(mongo_url)


def generate_vote_hash(votation_ids: List[int], calculation_params: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate a stable hash for a set of votation IDs and calculation parameters.
    
    Args:
        votation_ids: List of votation IDs
        calculation_params: Optional calculation parameters to include in hash
        
    Returns:
        SHA256 hash string for the combination
    """
    # Sort votation IDs to ensure consistent ordering
    sorted_ids = sorted(votation_ids)
    
    # Create hash input string
    hash_input = ",".join(map(str, sorted_ids))
    
    # Include calculation parameters if provided
    if calculation_params:
        # Sort parameters for consistent hashing
        sorted_params = sorted(calculation_params.items())
        params_str = ",".join(f"{k}:{v}" for k, v in sorted_params)
        hash_input += f"|{params_str}"
    
    # Generate SHA256 hash
    hash_object = hashlib.sha256(hash_input.encode('utf-8'))
    return hash_object.hexdigest()


def check_existing_result(result_hash: str, db_name: str = "quevotanEtiquetado") -> Optional[Dict[str, Any]]:
    """
    Check if a W-NOMINATE result already exists for the given hash.
    
    Args:
        result_hash: The hash of the votation IDs and parameters
        db_name: Name of the MongoDB database
        
    Returns:
        Existing result if found, None otherwise
    """
    client = get_mongodb_connection()
    db = client[db_name]
    results_collection = db["dwnominate_calculations"]
    
    existing_result = results_collection.find_one({"result_hash": result_hash})
    
    if existing_result:
        # Update access tracking
        results_collection.update_one(
            {"result_hash": result_hash},
            {
                "$set": {"last_accessed": datetime.datetime.utcnow()},
                "$inc": {"access_count": 1}
            }
        )
        print(f"Found cached result for hash: {result_hash}")
        return existing_result.get("results")
    
    return None


def store_wnominate_result(
    result_hash: str,
    votation_ids: List[int],
    calculation_params: Dict[str, Any],
    results: Dict[str, Any],
    db_name: str = "quevotanEtiquetado"
) -> bool:
    """
    Store W-NOMINATE calculation results in MongoDB.
    
    Args:
        result_hash: The hash identifying this calculation
        votation_ids: List of votation IDs used
        calculation_params: Parameters used for calculation
        results: The W-NOMINATE calculation results
        db_name: Name of the MongoDB database
        
    Returns:
        True if successfully stored, False otherwise
    """
    try:
        client = get_mongodb_connection()
        db = client[db_name]
        results_collection = db["dwnominate_calculations"]
        
        # Prepare document for storage
        result_document = {
            "result_hash": result_hash,
            "votation_ids": sorted(votation_ids),  # Store sorted for consistency
            "votation_count": len(votation_ids),
            "calculation_params": calculation_params,
            "results": results,
            "created_at": datetime.datetime.utcnow(),
            "last_accessed": datetime.datetime.utcnow(),
            "access_count": 1
        }
        
        # Store the result
        results_collection.insert_one(result_document)
        print(f"Stored result with hash: {result_hash}")
        return True
        
    except Exception as e:
        print(f"Error storing result: {e}")
        return False


def create_wnominate_indexes(db_name: str = "quevotanEtiquetado") -> None:
    """
    Create indexes for the dwnominate_calculations collection for optimal performance.
    
    Args:
        db_name: Name of the MongoDB database
    """
    try:
        client = get_mongodb_connection()
        db = client[db_name]
        results_collection = db["dwnominate_calculations"]
        
        # Create indexes
        results_collection.create_index("result_hash", unique=True)
        results_collection.create_index("created_at")
        results_collection.create_index("votation_count")
        results_collection.create_index("last_accessed")
        
        print("Created indexes for dwnominate_calculations collection")
        
    except Exception as e:
        print(f"Error creating indexes: {e}")


def cleanup_old_results(
    days_old: int = 30,
    db_name: str = "quevotanEtiquetado"
) -> int:
    """
    Clean up old W-NOMINATE results that haven't been accessed recently.
    
    Args:
        days_old: Remove results older than this many days
        db_name: Name of the MongoDB database
        
    Returns:
        Number of results removed
    """
    try:
        client = get_mongodb_connection()
        db = client[db_name]
        results_collection = db["dwnominate_calculations"]
        
        cutoff_date = datetime.datetime.utcnow() - datetime.timedelta(days=days_old)
        
        result = results_collection.delete_many({
            "last_accessed": {"$lt": cutoff_date}
        })
        
        print(f"Cleaned up {result.deleted_count} old results")
        return result.deleted_count
        
    except Exception as e:
        print(f"Error cleaning up results: {e}")
        return 0


def generate_payload(votation_ids: List[int], db_name: str = "quevotanEtiquetado") -> Dict[str, Any]:
    """
    Generate a payload for the W-NOMINATE calculation based on a list of votation IDs.
    
    Args:
        votation_ids: List of votation IDs to include in the payload
        db_name: Name of the MongoDB database to connect to
        
    Returns:
        Dict containing the generated payload
    """
    # Connect to MongoDB
    client = get_mongodb_connection()
    db = client[db_name]
    
    votos_diputados = db["VotosDiputados"]
    parlamentarios = db["parlamentarios"]
    votaciones = db["votaciones"]
    
    print(f"Original votation ID order: {votation_ids}")
    
    # Get all parliamentarians
    todos_diputados = list(parlamentarios.find())
    
    # Get requested votations
    votaciones_list = list(votaciones.find({"id": {"$in": votation_ids}}))
    
    # Sort votations by date if available
    if votaciones_list and all('fecha' in v for v in votaciones_list):
        votaciones_list.sort(key=lambda x: x['fecha'])
        print(f"Sorted votations by date: {[v['id'] for v in votaciones_list]}")
    else:
        # If dates not available, try to preserve the original order
        votation_id_to_index = {id: i for i, id in enumerate(votation_ids)}
        votaciones_list.sort(key=lambda x: votation_id_to_index.get(x.get('id', 0), 999999))
        print(f"Preserved original order: {[v['id'] for v in votaciones_list]}")
    
    # Initialize payload structure
    payload = {
        'votes': [],
        'memberwise': [],
        'idpt': {},
        'bp': {},
        'bw': {'b': 8.8633, 'w': 0.4619}  # Default values
    }
    
    votos_por_diputado = {}
    
    # Process each votation
    print(f"Processing votations in this order:")
    for idx, votacion in enumerate(votaciones_list):
        vot_id = votacion["id"]
        print(f"  {idx+1}. ID: {vot_id}" + (f", Date: {votacion.get('fecha', 'N/A')}" if 'fecha' in votacion else ""))
        voto_doc = votos_diputados.find_one({"id": vot_id})
        
        if not voto_doc:
            print(f"Warning: No vote data found for votation ID {vot_id}")
            continue
            
        detalle = voto_doc.get("detalle", {})
        votos = []
        
        # Process votes for each parliamentarian
        for diputado in todos_diputados:
            dip_id_str = str(diputado.get("id"))
            miembro = f"M{dip_id_str}"
            
            # Get vote if exists; otherwise abstention/absent (2)
            voto_original = detalle.get(dip_id_str, 2)
            voto_mapeado = mapear_voto(voto_original)
            votos.append((voto_mapeado, miembro))
            
            # Add to memberwise
            if miembro not in votos_por_diputado:
                votos_por_diputado[miembro] = []
            votos_por_diputado[miembro].append((voto_mapeado, f"V{vot_id}"))
            
            # Initialize idpt if not already
            if miembro not in payload['idpt']:
                payload['idpt'][miembro] = [0.0, 0.0]
        
        # Add votation to payload
        payload['votes'].append({
            'id': f"V{vot_id}",
            'update': True,
            'votes': votos
        })
        
        # Set bp parameter
        payload['bp'][f"V{vot_id}"] = [0.0, 0.0, 0.1, 0.1]  # Default values
    
    # Verify the order in the final payload
    payload_votation_order = [int(v['id'][1:]) for v in payload['votes']]
    print(f"Final payload votation order: {payload_votation_order}")
    
    # Build memberwise
    for member_id, votos in votos_por_diputado.items():
        payload['memberwise'].append({
            'icpsr': member_id,
            'update': True,
            'votes': votos
        })
    
    return payload


def mapear_voto(valor: int) -> int:
    """
    Map original vote values to W-NOMINATE format.
    
    Args:
        valor: Original vote value
        
    Returns:
        Mapped vote value: 1 (Yes), -1 (No), 0 (Abstention/Absent)
    """
    if valor == 1:
        return 1   # Yes
    elif valor == 0:
        return -1  # No
    else:
        return 0   # Abstention or Absent


def run_wnominate(
    payload: Dict[str, Any],
    maxiter: int = 30,
    cores: int = 1,
    xtol: float = 1e-4,
    update: List[str] = None,
    add_meta: List[str] = None
) -> Dict[str, Any]:
    """
    Run the W-NOMINATE calculation with the provided payload.
    
    Args:
        payload: Payload data for W-NOMINATE calculation
        maxiter: Maximum number of iterations
        cores: Number of CPU cores to use
        xtol: Convergence tolerance
        update: List of parameters to update
        add_meta: Additional metadata to include
        
    Returns:
        Dict containing the W-NOMINATE calculation results
    """
    if update is None:
        update = ["bp", "idpt", "bw"]
    
    if add_meta is None:
        add_meta = []
    
    # Convert lists in payload to numpy arrays where needed
    processed_payload = {
        "votes": payload["votes"],
        "memberwise": payload["memberwise"],
        "idpt": {k: np.array(v) for k, v in payload["idpt"].items()},
        "bp": {k: np.array(v) for k, v in payload["bp"].items()},
        "bw": {
            "b": float(payload["bw"]["b"]),
            "w": float(payload["bw"]["w"])
        }
    }
    
    # Run the W-NOMINATE calculation
    result = update_nominate(
        processed_payload,
        maxiter=maxiter,
        cores=cores,
        update=update,
        xtol=xtol,
        add_meta=add_meta
    )
    
    return result


def format_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format the results from update_nominate for clean API consumption.
    Converts numpy arrays to lists, removes prefixes, and ensures JSON serializable structure.
    
    Args:
        results: Results from update_nominate
        
    Returns:
        Dict containing clean formatted results ready for JSON serialization
    """
    formatted = {}
    
    # Process idpt (coordinates for each parliamentarian)
    # Remove 'M' prefix and store clean congressman IDs with simplified structure
    if 'idpt' in results:
        formatted['idpt'] = {}
        for member_id, member_data in results['idpt'].items():
            # Remove 'M' prefix to get clean congressman ID
            clean_id = member_id[1:] if member_id.startswith('M') else member_id
            
            # Extract coordinates from the nested structure
            if isinstance(member_data, dict) and 'idpt' in member_data:
                # Handle nested structure: {"idpt": [x, y], "meta": {...}}
                coords = member_data['idpt']
            else:
                # Handle direct coordinate structure: [x, y]
                coords = member_data
            
            # Convert numpy arrays to lists and create clean structure
            if isinstance(coords, np.ndarray):
                coords_list = coords.tolist()
            else:
                coords_list = coords if isinstance(coords, list) else [coords]
            
            # Store as xcoord, ycoord structure
            if len(coords_list) >= 2:
                formatted['idpt'][clean_id] = {
                    "xcoord": coords_list[0],
                    "ycoord": coords_list[1]
                }
            else:
                # Fallback in case of unexpected structure
                formatted['idpt'][clean_id] = {
                    "xcoord": coords_list[0] if len(coords_list) > 0 else 0.0,
                    "ycoord": 0.0
                }
    
    # Process bp (bill parameters for each vote)
    # Remove 'V' prefix and store clean votation IDs
    if 'bp' in results:
        formatted['bp'] = {}
        for vote_id, params in results['bp'].items():
            # Remove 'V' prefix to get clean votation ID
            clean_vote_id = vote_id[1:] if vote_id.startswith('V') else vote_id
            
            if isinstance(params, np.ndarray):
                formatted['bp'][clean_vote_id] = params.tolist()
            else:
                formatted['bp'][clean_vote_id] = params
    
    # Add global parameters (b and w)
    if 'bw' in results:
        formatted['bw'] = results['bw']
    
    # Add metadata if present
    if 'meta' in results:
        formatted['meta'] = results['meta']
    
    return formatted


def get_congressman_details(congressman_ids: List[str], db_name: str = "quevotanEtiquetado") -> Dict[str, Dict[str, Any]]:
    """
    Fetch congressman details for the given IDs from the parlamentarios collection.
    
    Args:
        congressman_ids: List of congressman IDs (as strings)
        db_name: Name of the MongoDB database
        
    Returns:
        Dict mapping congressman ID to their details
    """
    client = get_mongodb_connection()
    db = client[db_name]
    parlamentarios = db["parlamentarios"]
    
    # Convert IDs to integers for MongoDB query
    int_ids = [int(id) for id in congressman_ids]
    
    # Fetch congressman details
    congressmen = parlamentarios.find({"id": {"$in": int_ids}})
    
    details = {}
    for congressman in congressmen:
        details[str(congressman["id"])] = {
            "id": congressman["id"],
            "nombre": congressman.get("nombre", ""),
            "apellido": congressman.get("apellido", ""),
            "partido": congressman.get("partido", ""),
            "periodo": congressman.get("periodo", ""),
            # Add any other fields you need
        }
    
    return details


def get_votation_details(votation_ids: List[str], db_name: str = "quevotanEtiquetado") -> Dict[str, Dict[str, Any]]:
    """
    Fetch votation details for the given IDs from the votaciones collection.
    
    Args:
        votation_ids: List of votation IDs (as strings)
        db_name: Name of the MongoDB database
        
    Returns:
        Dict mapping votation ID to their details
    """
    client = get_mongodb_connection()
    db = client[db_name]
    votaciones = db["votaciones"]
    
    # Convert IDs to integers for MongoDB query
    int_ids = [int(id) for id in votation_ids]
    
    # Fetch votation details
    votations = votaciones.find({"id": {"$in": int_ids}})
    
    details = {}
    for votation in votations:
        details[str(votation["id"])] = {
            "id": votation["id"],
            "nombre": votation.get("nombre", ""),
            "boletin": votation.get("boletin", ""),
            "fecha": votation.get("fecha", ""),
            "descripcion": votation.get("descripcion", ""),
            # Add any other fields you need
        }
    
    return details


def create_enriched_result(
    wnominate_result: Dict[str, Any], 
    include_details: bool = False,
    db_name: str = "quevotanEtiquetado"
) -> Dict[str, Any]:
    """
    Create an enriched W-NOMINATE result with optional congressman and votation details.
    
    Args:
        wnominate_result: The clean W-NOMINATE result
        include_details: Whether to include congressman and votation details
        db_name: Name of the MongoDB database
        
    Returns:
        Enriched result with optional details
    """
    enriched = wnominate_result.copy()
    
    if include_details and 'idpt' in wnominate_result and 'bp' in wnominate_result:
        # Get congressman details
        congressman_ids = list(wnominate_result['idpt'].keys())
        congressman_details = get_congressman_details(congressman_ids, db_name)
        
        # Get votation details  
        votation_ids = list(wnominate_result['bp'].keys())
        votation_details = get_votation_details(votation_ids, db_name)
        
        # Add details to result
        enriched['congressman_details'] = congressman_details
        enriched['votation_details'] = votation_details
    
    return enriched


def calculate_wnominate_with_storage(
    votation_ids: List[int],
    db_name: str = "quevotanEtiquetado",
    maxiter: int = 30,
    cores: int = 1,
    xtol: float = 1e-4,
    force_recalculate: bool = False
) -> Dict[str, Any]:
    """
    End-to-end function to calculate W-NOMINATE with automatic storage and caching.
    
    Args:
        votation_ids: List of votation IDs to include in the calculation
        db_name: Name of the MongoDB database
        maxiter: Maximum number of iterations
        cores: Number of CPU cores to use
        xtol: Convergence tolerance
        force_recalculate: If True, bypass cache and recalculate
        
    Returns:
        Dict containing:
        - 'result_hash': The hash for this calculation
        - 'cached': Whether result was from cache
        - 'results': The W-NOMINATE calculation results
    """
    # Prepare calculation parameters for hashing
    calculation_params = {
        'maxiter': maxiter,
        'cores': cores,
        'xtol': xtol,
        'db_name': db_name
    }
    
    # Generate hash for this calculation
    result_hash = generate_vote_hash(votation_ids, calculation_params)
    print(f"Generated hash for calculation: {result_hash}")
    
    # Check for existing result unless forced to recalculate
    if not force_recalculate:
        existing_result = check_existing_result(result_hash, db_name)
        if existing_result:
            return {
                'result_hash': result_hash,
                'cached': True,
                'results': existing_result
            }
    
    print("No cached result found, performing calculation...")
    
    # Perform the calculation
    results = calculate_wnominate(
        votation_ids=votation_ids,
        db_name=db_name,
        maxiter=maxiter,
        cores=cores,
        xtol=xtol
    )
    
    # Store the results
    storage_success = store_wnominate_result(
        result_hash=result_hash,
        votation_ids=votation_ids,
        calculation_params=calculation_params,
        results=results,
        db_name=db_name
    )
    
    if not storage_success:
        print("Warning: Failed to store results in database")
    
    return {
        'result_hash': result_hash,
        'cached': False,
        'results': results
    }


def calculate_wnominate(
    votation_ids: List[int],
    db_name: str = "quevotanEtiquetado",
    maxiter: int = 30,
    cores: int = 1,
    xtol: float = 1e-4
) -> Dict[str, Any]:
    """
    End-to-end function to calculate W-NOMINATE for a given list of votation IDs.
    
    Args:
        votation_ids: List of votation IDs to include in the calculation
        db_name: Name of the MongoDB database
        maxiter: Maximum number of iterations
        cores: Number of CPU cores to use
        xtol: Convergence tolerance
        
    Returns:
        Dict containing the W-NOMINATE calculation results
    """
    # Generate payload from MongoDB data
    payload = generate_payload(votation_ids, db_name)
    
    # Run W-NOMINATE calculation
    results = run_wnominate(
        payload,
        maxiter=maxiter,
        cores=cores,
        xtol=xtol
    )
    
    # Format results for API consumption
    formatted_results = format_results(results)
    
    return formatted_results


def save_results_to_file(results: Dict[str, Any], output_file: str) -> None:
    """
    Save results to a JSON file.
    
    Args:
        results: Results to save
        output_file: Path to the output file
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def parse_arguments():
    """
    Parse command line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Calculate W-NOMINATE for a set of votation IDs')
    
    parser.add_argument(
        '--votation-ids',
        type=int,
        nargs='+',
        required=True,
        help='List of votation IDs to include in the calculation'
    )
    
    parser.add_argument(
        '--db-name',
        type=str,
        default="quevotanEtiquetado",
        help='Name of the MongoDB database'
    )
    
    parser.add_argument(
        '--maxiter',
        type=int,
        default=10,
        help='Maximum number of iterations'
    )
    
    parser.add_argument(
        '--cores',
        type=int,
        default=1,
        help='Number of CPU cores to use'
    )
    
    parser.add_argument(
        '--xtol',
        type=float,
        default=1e-4,
        help='Convergence tolerance'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Path to the output JSON file (if not specified, prints to stdout)'
    )
    parser.add_argument(
        '--force-recalculate',
        action='store_true',
        help='Force recalculation even if cached result exists'
    )
    
    parser.add_argument(
        '--cleanup-days',
        type=int,
        help='Clean up results older than this many days'
    )
    
    parser.add_argument(
        '--create-indexes',
        action='store_true',
        help='Create database indexes for optimal performance'
    )
    
    parser.add_argument(
        '--include-details',
        action='store_true',
        help='Include congressman and votation details in the output'
    )
    
    return parser.parse_args()


def main():
    """
    Main function for CLI usage.
    """
    args = parse_arguments()
    
    try:
        # Handle utility operations first
        if args.create_indexes:
            create_wnominate_indexes(args.db_name)
            return
            
        if args.cleanup_days:
            cleanup_old_results(args.cleanup_days, args.db_name)
            return
        
        # Calculate W-NOMINATE with storage
        calculation_result = calculate_wnominate_with_storage(
            votation_ids=args.votation_ids,
            db_name=args.db_name,
            maxiter=args.maxiter,
            cores=args.cores,
            xtol=args.xtol,
            force_recalculate=args.force_recalculate
        )
        
        # Prepare output
        output_data = {
            'result_hash': calculation_result['result_hash'],
            'cached': calculation_result['cached'],
            'results': calculation_result['results']
        }
        
        # Enrich with details if requested
        if args.include_details:
            output_data['results'] = create_enriched_result(
                output_data['results'], 
                include_details=True,
                db_name=args.db_name
            )
        
        # Save or print results
        if args.output:
            save_results_to_file(output_data, args.output)
            print(f"Results saved to {args.output}")
        else:
            print(json.dumps(output_data, indent=2))
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
