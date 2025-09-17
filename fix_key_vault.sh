# Create the fix script
cat > fix_key_vault.sh << 'EOF'
#!/bin/bash

echo "🔧 Updating Key Vault with current working storage key..."

# Use key1 from your storage account output
STORAGE_KEY="EQHuEWbZfLRfD+jHJfpvJOETFTEcVPtU8th3oyb8EAePUuPTxJcqAaG3sPdk3sZ8ZNW9v5x00osY+AStbwEsiQ=="

echo "🔐 Updating Key Vault secret..."
az keyvault secret set \
    --vault-name ainldas34754142228 \
    --name blob-storage \
    --value "$STORAGE_KEY"

echo "✅ Key Vault secret updated successfully"

# Verify the update
echo "🧪 Verifying the update..."
VAULT_KEY=$(az keyvault secret show \
    --vault-name ainldas34754142228 \
    --name blob-storage \
    --query 'value' \
    --output tsv)

if [ "$STORAGE_KEY" = "$VAULT_KEY" ]; then
    echo "✅ Verification successful - keys match"
    echo "🎉 Storage account key fix completed!"
    echo "🔄 Restart your Azure Functions to use the updated key"
else
    echo "❌ Verification failed - keys don't match"
    echo "Storage key: ${STORAGE_KEY:0:20}..."
    echo "Vault key: ${VAULT_KEY:0:20}..."
    exit 1
fi
EOF

# Make it executable
chmod +x fix_key_vault.sh

# Run it
./fix_key_vault.sh