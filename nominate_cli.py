#!/usr/bin/env python
"""
W-NOMINATE CLI

A command-line interface for calculating W-NOMINATE coordinates based on a list of votation IDs.
This script is a wrapper around the wnominate_api module.
"""

import sys
import argparse
from wnominate_api import calculate_wnominate, save_results_to_file


def parse_arguments():
    """
    Parse command line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Calculate W-NOMINATE coordinates for a set of votation IDs'
    )
    
    parser.add_argument(
        'votation_ids',
        type=int,
        nargs='+',
        help='List of votation IDs to include in the calculation'
    )
    
    parser.add_argument(
        '--db-name',
        type=str,
        default="quevotanEtiquetado",
        help='Name of the MongoDB database (default: quevotanEtiquetado)'
    )
    
    parser.add_argument(
        '--maxiter',
        type=int,
        default=30,
        help='Maximum number of iterations (default: 30)'
    )
    
    parser.add_argument(
        '--cores',
        type=int,
        default=1,
        help='Number of CPU cores to use (default: 1)'
    )
    
    parser.add_argument(
        '--xtol',
        type=float,
        default=1e-4,
        help='Convergence tolerance (default: 1e-4)'
    )
    
    parser.add_argument(
        '-o', '--output',
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
        print(f"Calculating W-NOMINATE for votation IDs: {args.votation_ids}", file=sys.stderr)
        
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
            print(f"Results saved to {args.output}", file=sys.stderr)
        else:
            import json
            print(json.dumps(results, indent=2))
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
