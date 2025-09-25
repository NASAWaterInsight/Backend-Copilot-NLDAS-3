#!/bin/bash

echo "🔧 FIXING GRAY AREA - Complete Agent Refresh"

# Stop any running functions
echo "🛑 Stopping functions..."
pkill -f "func" 2>/dev/null || echo "No functions running"

# Wait a moment for processes to stop
sleep 2

# Recreate agent with fixed instructions
echo "🤖 Recreating agent with gray area fixes..."
python3 agents/agent_creation.py

if [ $? -eq 0 ]; then
    echo "✅ Agent recreated successfully"
else
    echo "❌ Agent recreation failed"
    exit 1
fi

# Wait a moment
sleep 1

# Restart functions
echo "🚀 Restarting functions..."
func start --verbose &

# Wait for functions to start
echo "⏳ Waiting for functions to start..."
sleep 5

echo ""
echo "🎉 Gray area fix complete!"
echo ""
echo "📋 What was fixed:"
echo "  ✅ Added ax.background_patch.set_visible(False)"
echo "  ✅ Added fig.patch.set_facecolor('white')"
echo "  ✅ Set facecolor='none', edgecolor='color' for all features"
echo ""
echo "🧪 Test with:"
echo "  'show me the map of the average temperature in Florida in Jan 21, 2023'"
echo ""
echo "🔍 If gray area persists, check:"
echo "  1. Agent was recreated (check agent_info.json timestamp)"
echo "  2. Functions restarted (check terminal output)"
echo "  3. All code examples in agent instructions are updated"