# diagnostic_check.py
from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient
import fsspec

# Your credentials
TENANT_ID = "4ba2629f-3085-4f9a-b2ec-3962de0e3490"
CLIENT_ID = "768b7315-6661-498c-b826-c2689a5d790e"
CLIENT_SECRET = "l._8Q~bLceP-UjSOiTyil2~dAe92MPW6htpBFblU"
VAULT_URL = "https://ainldas34754142228.vault.azure.net/"
VAULT_SECRET = "blob-storage"
ACCOUNT_NAME = "ainldas34950184597"

# Get account key
cred = ClientSecretCredential(tenant_id=TENANT_ID, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
account_key = SecretClient(vault_url=VAULT_URL, credential=cred).get_secret(VAULT_SECRET).value

# Check source NetCDF files
fs_read = fsspec.filesystem("az", account_name=ACCOUNT_NAME, account_key=account_key)
netcdf_pattern = "nldas-3-forcing/NLDAS_FOR0010_H.A202301*.nc"
netcdf_files = sorted(fs_read.glob(netcdf_pattern))

print("=== SOURCE NETCDF FILES ===")
print(f"Pattern: {netcdf_pattern}")
print(f"Found {len(netcdf_files)} NetCDF files:")
for i, f in enumerate(netcdf_files[-10:]):  # Show last 10
    print(f"  {i+1}. {f}")

# Check kerchunk JSON files
fs_rw = fsspec.filesystem("abfs", account_name=ACCOUNT_NAME, account_key=account_key)
kerchunk_container = "kerchunk"

try:
    kerchunk_entries = fs_rw.ls(kerchunk_container)
    kerchunk_jsons = [e for e in kerchunk_entries if e.endswith(".json") and not e.endswith("combined.json")]
    
    print(f"\n=== KERCHUNK JSON FILES ===")
    print(f"Found {len(kerchunk_jsons)} kerchunk JSON files:")
    for i, f in enumerate(sorted(kerchunk_jsons)[-10:]):  # Show last 10
        filename = f.split("/")[-1]
        print(f"  {i+1}. {filename}")
        
except Exception as e:
    print(f"Error checking kerchunk files: {e}")