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
    Format the results from update_nominate for API consumption.
    Converts numpy arrays to lists and ensures the result is JSON serializable.
    
    Args:
        results: Results from update_nominate
        
    Returns:
        Dict containing formatted results ready for JSON serialization
    """
    formatted = {}
    
    # Process idpt (coordinates for each parliamentarian)
    if 'idpt' in results:
        formatted['idpt'] = {}
        for member_id, coords in results['idpt'].items():
            # Convert numpy arrays to lists for JSON serialization
            if isinstance(coords, np.ndarray):
                formatted['idpt'][member_id] = coords.tolist()
            else:
                formatted['idpt'][member_id] = coords
    
    # Process other result components if needed
    if 'bp' in results:
        formatted['bp'] = {}
        for vote_id, params in results['bp'].items():
            if isinstance(params, np.ndarray):
                formatted['bp'][vote_id] = params.tolist()
            else:
                formatted['bp'][vote_id] = params
    
    # Add any other result components that are needed for visualization
    if 'bw' in results:
        formatted['bw'] = results['bw']
    
    # Add metadata if present
    if 'meta' in results:
        formatted['meta'] = results['meta']
    
    return formatted


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
    
    return parser.parse_args()


def main():
    """
    Main function for CLI usage.
    """
    args = parse_arguments()
    
    try:
        # Calculate W-NOMINATE
        results = calculate_wnominate(
            votation_ids=args.votation_ids,
            db_name=args.db_name,
            maxiter=args.maxiter,
            cores=args.cores,
            xtol=args.xtol
        )
        
        # Save or print results
        if args.output:
            save_results_to_file(results, args.output)
            print(f"Results saved to {args.output}")
        else:
            print(json.dumps(results, indent=2))
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
