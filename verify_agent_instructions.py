import os
import json
import requests
import time

def test_agent_cartopy_capability():
    """Test if the agent can successfully use Cartopy for geographic plotting"""
    
    print("🗺️  Testing Agent Cartopy Capabilities...")
    
    # Test query that should require Cartopy
    test_query = {
        "action": "generate", 
        "data": {
            "query": "Create a map of Maryland showing the precipitation data with state boundaries using Cartopy. Include coastlines and state borders."
        }
    }
    
    try:
        # Send request to your Azure Function
        url = "http://localhost:7071/api/chat"  # Adjust if different
        
        print("📡 Sending Cartopy test query to agent...")
        response = requests.post(url, json=test_query, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            
            # Check if the response contains Cartopy-related code
            python_code = result.get('data', {}).get('python_code', '')
            
            cartopy_indicators = [
                'import cartopy',
                'cartopy.crs',
                'cartopy.feature',
                'PlateCarree',
                'add_feature',
                'coastlines',
                'borders'
            ]
            
            cartopy_found = [indicator for indicator in cartopy_indicators if indicator in python_code]
            
            if cartopy_found:
                print("✅ SUCCESS: Agent generated Cartopy code!")
                print(f"🎯 Found Cartopy features: {', '.join(cartopy_found)}")
                
                # Check if code executed successfully
                execution_status = result.get('data', {}).get('status')
                if execution_status == 'success':
                    print("✅ Code executed successfully!")
                    return True
                else:
                    print("⚠️  Code generated but execution failed")
                    print(f"Error: {result.get('data', {}).get('error', 'Unknown error')}")
                    return False
            else:
                print("❌ FAILED: No Cartopy code found in response")
                print("Generated code preview:")
                print(python_code[:500] + "..." if len(python_code) > 500 else python_code)
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            print(response.text)
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def check_cartopy_installation():
    """Check if Cartopy is installed in the environment"""
    print("🔍 Checking Cartopy installation...")
    
    try:
        import cartopy
        print(f"✅ Cartopy version {cartopy.__version__} is installed")
        
        # Test basic Cartopy functionality
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        print("✅ Cartopy imports working")
        
        return True
    except ImportError as e:
        print(f"❌ Cartopy not installed: {e}")
        print("💡 Install with: pip install cartopy")
        return False
    except Exception as e:
        print(f"❌ Cartopy import error: {e}")
        return False

def verify_requirements_txt():
    """Check if cartopy is in requirements.txt"""
    print("📋 Checking requirements.txt...")
    
    requirements_file = "requirements.txt"
    if os.path.exists(requirements_file):
        with open(requirements_file, 'r') as f:
            content = f.read().lower()
            
        if 'cartopy' in content:
            print("✅ Cartopy found in requirements.txt")
            return True
        else:
            print("❌ Cartopy not found in requirements.txt")
            print("💡 Add 'cartopy>=0.21.0' to requirements.txt")
            return False
    else:
        print("❌ requirements.txt not found")
        return False

def main():
    """Run all Cartopy verification tests"""
    print("=" * 60)
    print("🗺️  AGENT CARTOPY CAPABILITY VERIFICATION")
    print("=" * 60)
    
    # Test 1: Check installation
    cartopy_installed = check_cartopy_installation()
    print()
    
    # Test 2: Check requirements.txt
    cartopy_in_requirements = verify_requirements_txt()
    print()
    
    # Test 3: Test agent capability (only if installed)
    if cartopy_installed:
        agent_can_use_cartopy = test_agent_cartopy_capability()
    else:
        print("⏭️  Skipping agent test - Cartopy not installed")
        agent_can_use_cartopy = False
    
    print("\n" + "=" * 60)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Cartopy Installed: {'✅' if cartopy_installed else '❌'}")
    print(f"In requirements.txt: {'✅' if cartopy_in_requirements else '❌'}")
    print(f"Agent can use Cartopy: {'✅' if agent_can_use_cartopy else '❌'}")
    
    if all([cartopy_installed, cartopy_in_requirements, agent_can_use_cartopy]):
        print("\n🎉 SUCCESS: Agent is fully capable of using Cartopy!")
        return True
    else:
        print("\n⚠️  ISSUES DETECTED: Agent may not be able to use Cartopy properly")
        
        # Provide fix suggestions
        if not cartopy_installed:
            print("🔧 Fix: pip install cartopy")
        if not cartopy_in_requirements:
            print("🔧 Fix: Add 'cartopy>=0.21.0' to requirements.txt")
        
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)