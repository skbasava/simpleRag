#!/usr/bin/env python3
"""
IPCAT Policy Fetcher using pass for credentials and direct requests
"""

import subprocess
import sys
import json
import requests
from urllib.parse import urljoin

# Configuration
BASE_URL = "https://ipcatalog.qualcomm.com"
USERNAME = "satibasa"
PASS_PATH = "ipcat-tool/satibasa"

def get_password_from_pass(pass_name):
    """Retrieve password from pass"""
    try:
        result = subprocess.run(
            ['pass', 'show', pass_name],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        password = result.stdout.strip()
        if not password:
            raise ValueError("Password is empty")
        return password
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving password: {e.stderr}")
        return None
    except subprocess.TimeoutExpired:
        print("Timeout retrieving password from pass")
        return None
    except FileNotFoundError:
        print("'pass' command not found. Please install pass.")
        return None
    except ValueError as e:
        print(f"Error: {e}")
        return None

class IPCATClient:
    """Direct IPCAT API client using requests"""
    
    def __init__(self, username, password, base_url=BASE_URL):
        self.username = username
        self.password = password
        self.base_url = base_url
        self.session = requests.Session()
        self.token = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate and get token"""
        print(f"Authenticating as {self.username}...")
        
        # Login endpoint
        login_url = urljoin(self.base_url, '/auth/token/login/')
        
        try:
            response = self.session.post(
                login_url,
                data={
                    'username': self.username,
                    'password': self.password
                },
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            self.token = data.get('token')
            
            if self.token:
                # Set token in session headers
                self.session.headers.update({
                    'Authorization': f'Token {self.token}'
                })
                print("Authentication successful!")
            else:
                raise ValueError("No token received from server")
                
        except requests.exceptions.RequestException as e:
            print(f"Authentication failed: {e}")
            raise
    
    def get_chip_policies(self, chip_id, xpu_id, policy_id=None, **params):
        """
        Get chip policies based on the URL pattern from browser
        
        URL pattern: /api/private/chip/{chip_id}/xpu_policies/{xpu_id}/parameters/{policy_id}
        
        Args:
            chip_id: Chip ID (e.g., 790)
            xpu_id: XPU ID (e.g., 6870)
            policy_id: Optional policy ID
            **params: Additional query parameters (xpu, map_version, etc.)
        """
        if policy_id:
            url = urljoin(
                self.base_url,
                f'/api/private/chip/{chip_id}/xpu_policies/{xpu_id}/parameters/{policy_id}'
            )
        else:
            url = urljoin(
                self.base_url,
                f'/api/private/chip/{chip_id}/xpu_policies/{xpu_id}/parameters/'
            )
        
        print(f"Fetching from: {url}")
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching policies: {e}")
            if hasattr(e.response, 'text'):
                print(f"Response: {e.response.text}")
            return None
    
    def get_chip_info(self, chip_id):
        """Get basic chip information"""
        url = urljoin(self.base_url, f'/api/private/chip/{chip_id}/')
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching chip info: {e}")
            return None
    
    def list_chips(self, **params):
        """List all chips"""
        url = urljoin(self.base_url, '/api/private/chip/')
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error listing chips: {e}")
            return None
    
    def get_xpu_policies(self, chip_id, **params):
        """Get XPU policies for a chip"""
        url = urljoin(self.base_url, f'/api/private/chip/{chip_id}/xpu_policies/')
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching XPU policies: {e}")
            return None

def save_to_file(data, filename):
    """Save data to JSON file"""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Data saved to {filename}")

def main():
    """Main function with example usage"""
    try:
        # Get password from pass
        print("Retrieving password from pass...")
        password = get_password_from_pass(PASS_PATH)
        
        if not password:
            print("Failed to retrieve password")
            return None
        
        # Initialize client
        client = IPCATClient(USERNAME, password)
        
        # Example 1: List all chips
        print("\n--- Example 1: Listing chips ---")
        chips = client.list_chips(limit=10)
        if chips:
            print(f"Found {chips.get('count', 0)} chips")
            for chip in chips.get('results', [])[:5]:
                print(f"  - ID: {chip.get('id')}, Name: {chip.get('name')}")
        
        # Example 2: Get specific chip info
        print("\n--- Example 2: Getting chip info ---")
        chip_id = 790  # From your screenshot
        chip_info = client.get_chip_info(chip_id)
        if chip_info:
            print(f"Chip Name: {chip_info.get('name')}")
            save_to_file(chip_info, f'chip_{chip_id}_info.json')
        
        # Example 3: Get XPU policies for a chip
        print("\n--- Example 3: Getting XPU policies ---")
        xpu_policies = client.get_xpu_policies(chip_id)
        if xpu_policies:
            print(f"XPU Policies count: {len(xpu_policies.get('results', []))}")
            save_to_file(xpu_policies, f'chip_{chip_id}_xpu_policies.json')
        
        # Example 4: Get specific policy parameters (from your screenshot)
        print("\n--- Example 4: Getting policy parameters ---")
        chip_id = 790
        xpu_id = 6870
        
        # Based on URL pattern from screenshot
        policies = client.get_chip_policies(
            chip_id=chip_id,
            xpu_id=xpu_id,
            xpu='AOSS_PERIPH_MPU_XPU48',
            map_version='52644'
        )
        
        if policies:
            print(f"Policies retrieved: {len(policies) if isinstance(policies, list) else 'Success'}")
            save_to_file(policies, f'chip_{chip_id}_xpu_{xpu_id}_policies.json')
        
        return policies
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    data = main()
