# deps: pip install azure-identity azure-keyvault-secrets azure-storage-blob fsspec adlfs kerchunk

import json
import argparse
from pathlib import Path
from typing import List

from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient
import fsspec
from kerchunk.hdf import SingleHdf5ToZarr
from kerchunk.combine import MultiZarrToZarr

# --- Credentials / config (adjust if you externalize later) ---
tenant_id   = "4ba2629f-3085-4f9a-b2ec-3962de0e3490"
client_id   = "768b7315-6661-498c-b826-c2689a5d790e"
client_secret = "l._8Q~bLceP-UjSOiTyil2~dAe92MPW6htpBFblU"
vault_url   = "https://ainldas34754142228.vault.azure.net/"
secret_name = "blob-storage"
account_name = "ainldas34950184597"

# Source data pattern (container/path)
default_blob_glob = "nldas-3-forcing/NLDAS_FOR0010_H.A202301*.nc"

# Destination containers
kerchunk_container = "kerchunk"
visualizations_container = "visualizations"

def get_account_key() -> str:
    cred = ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)
    return SecretClient(vault_url=vault_url, credential=cred).get_secret(secret_name).value

def ensure_container(account_key: str, container: str, public_access: bool = False):
    """
    Ensure container exists, with optional public access for visualizations
    """
    svc = BlobServiceClient(
        account_url=f"https://{account_name}.blob.core.windows.net",
        credential=account_key
    )
    client = svc.get_container_client(container)
    try:
        client.get_container_properties()
        print(f"Container '{container}' exists.")
    except Exception:
        print(f"Creating container '{container}'...")
        try:
            if public_access:
                # Try to create with public blob access first
                svc.create_container(container, public_access="blob")
                print(f"Created '{container}' with public blob access.")
            else:
                # Create private container
                svc.create_container(container)
                print(f"Created private container '{container}'.")
        except Exception as e:
            if "PublicAccessNotPermitted" in str(e):
                print(f"Public access not allowed on storage account. Creating private container '{container}'...")
                svc.create_container(container)
                print(f"Created private container '{container}' (images will need authentication to view).")
            else:
                raise e

def setup_containers(account_key: str):
    """
    Setup both kerchunk and visualizations containers
    """
    print("Setting up required containers...")
    
    # Create kerchunk container (private)
    ensure_container(account_key, kerchunk_container, public_access=False)
    
    # Create visualizations container (try public, fallback to private)
    ensure_container(account_key, visualizations_container, public_access=True)
    
    print("Container setup complete!")

def fs_read(account_key: str):
    return fsspec.filesystem("az", account_name=account_name, account_key=account_key)

def fs_rw(account_key: str):
    return fsspec.filesystem("abfs", account_name=account_name, account_key=account_key)

def list_source_files(fs, pattern: str) -> List[str]:
    paths = sorted(fs.glob(pattern))
    return [f"az://{p}" for p in paths]

def build_single(file_url: str, account_key: str) -> dict:
    storage_options = {"account_name": account_name, "account_key": account_key}
    return SingleHdf5ToZarr(file_url, storage_options=storage_options).translate()

def write_json_blob(fs_abfs, blob_path: str, obj: dict, overwrite: bool):
    if fs_abfs.exists(blob_path) and not overwrite:
        print(f"Skip (exists): {blob_path}")
        return False
    with fs_abfs.open(blob_path, "w") as f:
        json.dump(obj, f)
    return True

def combine_refs(individual_refs: List[dict]) -> dict:
    mzz = MultiZarrToZarr(
        individual_refs,
        remote_protocol="az",
        remote_options={},
        concat_dims=["time"]
    )
    return mzz.translate()

def setup_containers(account_key: str):
    """
    Setup both kerchunk and visualizations containers
    """
    print("Setting up required containers...")
    
    # Create kerchunk container (private)
    ensure_container(account_key, kerchunk_container, public_access=False)
    
    # Create visualizations container (public blob access)
    ensure_container(account_key, visualizations_container, public_access=True)
    
    print("Container setup complete!")

def main():
    parser = argparse.ArgumentParser(description="Create kerchunk JSONs and setup containers.")
    parser.add_argument("--pattern", default=default_blob_glob, help="Source glob (container/path/*.nc)")
    parser.add_argument("--limit", type=int, default=None, help="Process only first N files")
    parser.add_argument("--skip-combined", action="store_true", help="Do not build combined index")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing JSON blobs")
    parser.add_argument("--setup-only", action="store_true", help="Only setup containers, skip kerchunk processing")
    args = parser.parse_args()

    account_key = get_account_key()
    
    # Always setup containers first
    setup_containers(account_key)
    
    # If setup-only flag is used, exit after container setup
    if args.setup_only:
        print("Container setup completed. Use --setup-only=false to process kerchunk files.")
        return

    fs_src = fs_read(account_key)
    fs_dest = fs_rw(account_key)

    urls = list_source_files(fs_src, args.pattern)
    if not urls:
        print("No source NetCDF files found.")
        return
    if args.limit:
        urls = urls[:args.limit]
    print(f"Processing {len(urls)} NetCDF files")

    written = 0
    ref_objects = []
    for i, url in enumerate(urls, 1):
        blob_name = f"kerchunk_{Path(url).name.replace('.nc', '.json')}"
        dest_path = f"{kerchunk_container}/{blob_name}"
        try:
            refs = build_single(url, account_key)
            changed = write_json_blob(fs_dest, dest_path, refs, overwrite=args.overwrite)
            if changed:
                print(f"[{i}/{len(urls)}] Wrote {dest_path} | refs: {len(refs.get('refs', {}))}")
            else:
                print(f"[{i}/{len(urls)}] Cached {dest_path}")
            ref_objects.append(refs)
            written += 1
        except Exception as e:
            print(f"[{i}/{len(urls)}] FAILED {url}: {e}")

    if not args.skip_combined and ref_objects:
        combined_path = f"{kerchunk_container}/kerchunk_combined.json"
        try:
            combined = combine_refs(ref_objects)
            write_json_blob(fs_dest, combined_path, combined, overwrite=True)
            print(f"Combined index saved -> {combined_path} | refs: {len(combined.get('refs', {}))}")
        except Exception as e:
            print(f"Combine step skipped: {e}")

    # List summary
    try:
        entries = fs_dest.ls(kerchunk_container)
        json_blobs = [e for e in entries if e.endswith(".json")]
        print(f"\nSummary: {written} processed, {len(json_blobs)} JSON blobs now in '{kerchunk_container}'.")
        
        # Check visualizations container
        viz_entries = fs_dest.ls(visualizations_container) if fs_dest.exists(visualizations_container) else []
        print(f"Visualizations container ready with {len(viz_entries)} files.")
        
    except Exception as e:
        print(f"Could not list container summary: {e}")

if __name__ == "__main__":
    main()