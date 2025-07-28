#!/usr/bin/env python
"""
W-NOMINATE Graphing Module

This module provides a graphical interface for the W-NOMINATE calculations.
It leverages the wnominate_api.py pipeline to fetch and process the data,
and then plots the results using matplotlib.

Usage:
    python wnominate_graph.py --votation-ids 1,2,3,4,5
"""

import os
import sys
import json
import argparse
import matplotlib.pyplot as plt
import numpy as np
from typing import List, Dict, Any

# Import from the main module
from wnominate_api import calculate_wnominate


def parse_votation_ids(ids_str: str) -> List[int]:
    """
    Parse a comma-separated string of votation IDs into a list of integers.
    
    Args:
        ids_str: Comma-separated string of votation IDs
        
    Returns:
        List of integer votation IDs
    """
    try:
        return [int(id_str.strip()) for id_str in ids_str.split(',') if id_str.strip()]
    except ValueError:
        print("Error: Votation IDs must be integers separated by commas")
        sys.exit(1)


def generate_colors_by_party(idpt_results: Dict[str, List[float]], db_name: str = "quevotanEtiquetado") -> Dict[str, str]:
    """
    Generate a color mapping for each parliamentarian based on their party.
    
    Args:
        idpt_results: The W-NOMINATE coordinates for each parliamentarian
        db_name: Name of the MongoDB database
        
    Returns:
        Dictionary mapping parliamentarian IDs to colors
    """
    import pymongo
    from wnominate_api import get_mongodb_connection
    
    # Connect to MongoDB
    client = get_mongodb_connection()
    db = client[db_name]
    parlamentarios = db["parlamentarios"]
    
    # Define color mapping for parties
    party_colors = {
        "PC": "#0066FF",       # Partido Colorado (Blue)
        "PN": "#FFFFFF",       # Partido Nacional (White)
        "FA": "#FF0000",       # Frente Amplio (Red)
        "CA": "#FFD700",       # Cabildo Abierto (Yellow/Gold)
        "PI": "#FF6600",       # Partido Independiente (Orange)
        "PG": "#00CC00",       # Partido Verde (Green)
        "PERI": "#800080",     # Partido Ecologista Radical Intransigente (Purple)
        "AP": "#996633",       # Asamblea Popular (Brown)
        "PT": "#000000",       # Partido de los Trabajadores (Black)
        "UP": "#FF00FF",       # Unidad Popular (Magenta)
        "Default": "#CCCCCC"   # Default color for unknown parties (Gray)
    }
    
    # Create color mapping for each parliamentarian
    color_map = {}
    
    for member_id in idpt_results.keys():
        # Extract numeric ID from member ID (remove 'M' prefix)
        numeric_id = int(member_id[1:]) if member_id.startswith('M') else int(member_id)
        
        # Find parliamentarian in database
        parlamentario = parlamentarios.find_one({"id": numeric_id})
        
        if parlamentario and "partido" in parlamentario:
            partido = parlamentario["partido"]
            color_map[member_id] = party_colors.get(partido, party_colors["Default"])
        else:
            color_map[member_id] = party_colors["Default"]
    
    return color_map


def generate_labels(idpt_results: Dict[str, List[float]], db_name: str = "quevotanEtiquetado") -> Dict[str, str]:
    """
    Generate labels for each parliamentarian.
    
    Args:
        idpt_results: The W-NOMINATE coordinates for each parliamentarian
        db_name: Name of the MongoDB database
        
    Returns:
        Dictionary mapping parliamentarian IDs to labels
    """
    import pymongo
    from wnominate_api import get_mongodb_connection
    
    # Connect to MongoDB
    client = get_mongodb_connection()
    db = client[db_name]
    parlamentarios = db["parlamentarios"]
    
    # Create label mapping for each parliamentarian
    label_map = {}
    
    for member_id in idpt_results.keys():
        # Extract numeric ID from member ID (remove 'M' prefix)
        numeric_id = int(member_id[1:]) if member_id.startswith('M') else int(member_id)
        
        # Find parliamentarian in database
        parlamentario = parlamentarios.find_one({"id": numeric_id})
        
        if parlamentario and "nombre" in parlamentario:
            # Create a short label with name and party
            nombre = parlamentario.get("nombre", "Unknown")
            partido = parlamentario.get("partido", "")
            
            # Use last name or first part of the name to keep it short
            if " " in nombre:
                nombre = nombre.split(" ")[-1]  # Last name
            
            label_map[member_id] = f"{nombre} ({partido})"
        else:
            label_map[member_id] = member_id
    
    return label_map


def convert_to_plottable_format(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert the raw W-NOMINATE results to a format suitable for plotting.
    This is similar to what convert-json.py does.
    
    Args:
        results: Raw results from W-NOMINATE calculation
        
    Returns:
        Dict with simplified structure for plotting
    """
    converted = {"idpt": {}}
    
    if 'idpt' not in results:
        print("Error: No 'idpt' key found in results")
        print(f"Available keys: {list(results.keys())}")
        return converted
    
    idpt_data = results['idpt']
    
    for member_id, member_data in idpt_data.items():
        # Check if the data has the nested structure
        if isinstance(member_data, dict) and 'idpt' in member_data:
            # Extract coordinates from nested structure
            coords = member_data['idpt']
            # Convert numpy values to native Python floats if needed
            if hasattr(coords, '__iter__'):
                coords = [float(c) for c in coords]
            converted["idpt"][member_id] = coords
        else:
            # Data is already in the expected format
            converted["idpt"][member_id] = member_data
    
    return converted

def plot_wnominate_map(results: Dict[str, Any], output_file: str = None, show_labels: bool = True):
    """
    Plot the W-NOMINATE map with the calculated coordinates.
    
    Args:
        results: Results from calculate_wnominate
        output_file: Path to save the plot image (optional)
        show_labels: Whether to show labels for each point
    """
    # Convert raw results to plottable format
    converted_results = convert_to_plottable_format(results)
    
    if 'idpt' not in converted_results:
        print("Error: No IDPT coordinates found in converted results")
        return
        
    # Extract coordinates
    idpt = converted_results['idpt']
    
    # Check if there are valid coordinates
    if not idpt:
        print("Error: No valid coordinates found in converted results")
        return
        
    # Debug information about the structure
    print(f"Number of parliamentarians: {len(idpt)}")
    first_key = next(iter(idpt))
    print(f"Sample coordinate format for {first_key}: {idpt[first_key]}")
    
    # Check for degenerate case (all same values)
    all_coords = []
    for member_id, coords in idpt.items():
        # Handle both list and numpy array formats
        if isinstance(coords, (list, np.ndarray)) and len(coords) >= 2:
            # Extract as float values to ensure consistency
            x, y = float(coords[0]), float(coords[1])
            all_coords.append((x, y))
    
    if not all_coords:
        print("Error: No valid 2D coordinates found in converted results")
        # Show a sample of the data to help debug
        sample_data = {k: v for k, v in list(idpt.items())[:5]}
        print(f"Sample data: {sample_data}")
        return
        
    # Print success message
    print(f"Successfully extracted {len(all_coords)} valid coordinate pairs")
        
    # Check if all points are at the same coordinates (degenerate case)
    x_vals = [x for x, y in all_coords]
    y_vals = [y for x, y in all_coords]
    
    if len(set(x_vals)) <= 1 and len(set(y_vals)) <= 1:
        print("Warning: All points have the same coordinates. Plot may not be informative.")
    
    # Generate colors by party
    colors = generate_colors_by_party(idpt)
    
    # Generate labels
    labels = generate_labels(idpt) if show_labels else {}
    
    # Create figure
    plt.figure(figsize=(12, 10))
    
    # Plot each point
    for member_id, coords in idpt.items():
        # Handle both list and numpy array formats
        if isinstance(coords, (list, np.ndarray)) and len(coords) >= 2:
            # Extract as float values to ensure consistency
            x, y = float(coords[0]), float(coords[1])
            color = colors.get(member_id, "#CCCCCC")
            
            plt.scatter(x, y, color=color, s=100, edgecolors='black', alpha=0.7)
            
            if show_labels and member_id in labels:
                plt.annotate(labels[member_id], 
                             (x, y),
                             textcoords="offset points", 
                             xytext=(0, 5), 
                             ha='center',
                             fontsize=8)
    
    # Add reference lines
    plt.axhline(y=0, color='k', linestyle='-', alpha=0.3)
    plt.axvline(x=0, color='k', linestyle='-', alpha=0.3)
    
    # Add title and labels
    plt.title('W-NOMINATE Map', fontsize=16)
    plt.xlabel('First Dimension', fontsize=12)
    plt.ylabel('Second Dimension', fontsize=12)
    
    # Add grid
    plt.grid(True, linestyle='--', alpha=0.3)
    
    # Set equal aspect ratio only if we have varied coordinates
    if len(set(x_vals)) > 1 or len(set(y_vals)) > 1:
        plt.axis('equal')
    
    # Add border
    plt.gca().spines['top'].set_visible(True)
    plt.gca().spines['right'].set_visible(True)
    plt.gca().spines['bottom'].set_visible(True)
    plt.gca().spines['left'].set_visible(True)
    
    # Save or show plot
    if output_file:
        try:
            # Get absolute path for better reporting
            abs_path = os.path.abspath(output_file)
            plt.savefig(abs_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved successfully to: {abs_path}")
            
            # Verify file was created
            if os.path.exists(abs_path):
                file_size = os.path.getsize(abs_path)
                print(f"File size: {file_size} bytes")
            else:
                print("Warning: File was not created despite no errors")
        except Exception as e:
            print(f"Error saving plot: {str(e)}")
    else:
        plt.tight_layout()
        plt.show()


def parse_arguments():
    """
    Parse command line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Generate W-NOMINATE graph for a set of votation IDs')
    
    group = parser.add_mutually_exclusive_group(required=True)
    
    group.add_argument(
        '--votation-ids',
        type=str,
        help='Comma-separated list of votation IDs to include in the calculation'
    )
    
    group.add_argument(
        '--debug-file',
        type=str,
        help='Path to a pre-calculated JSON file with W-NOMINATE results to plot (bypasses calculation)'
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
        help='Path to save the plot image (if not specified, shows the plot)'
    )
    
    parser.add_argument(
        '--no-labels',
        action='store_true',
        help='Do not show labels on the plot'
    )
    
    return parser.parse_args()


def main():
    """
    Main function for CLI usage.
    """
    args = parse_arguments()
    
    try:
        # Check if we're debugging with a saved file
        if args.debug_file:
            print(f"Loading debug file: {args.debug_file}")
            with open(args.debug_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
            
            # Plot results
            plot_wnominate_map(
                results=results, 
                output_file=args.output,
                show_labels=not args.no_labels
            )
            return
            
        # Parse votation IDs
        votation_ids = parse_votation_ids(args.votation_ids)
        
        print(f"Calculating W-NOMINATE for votation IDs: {votation_ids}")
        
        # Calculate W-NOMINATE
        results = calculate_wnominate(
            votation_ids=votation_ids,
            db_name=args.db_name,
            maxiter=args.maxiter,
            cores=args.cores,
            xtol=args.xtol
        )
        
        # Check if results contain necessary data
        if not results or 'idpt' not in results or not results['idpt']:
            print("Warning: Calculation completed but no valid coordinates were generated.")
            print("Results structure:", json.dumps(results, indent=2, default=str)[:500] + "...")
            sys.exit(1)
            
        print(f"W-NOMINATE calculation completed. Found {len(results['idpt'])} parliamentarians with coordinates.")
        
        # Plot results
        plot_wnominate_map(
            results=results, 
            output_file=args.output,
            show_labels=not args.no_labels
        )
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
