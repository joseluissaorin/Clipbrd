import keyring
import requests
from supabase import create_client, Client
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
import os
import logging
from cryptography.fernet import Fernet
import json
import sys



# Initialize Windows keyring backend if on Windows
if sys.platform == 'win32':
    try:
        from keyring.backends import Windows
        keyring.set_keyring(Windows.WinVaultKeyring())
    except Exception as e:
        logging.error(f"Failed to initialize Windows keyring backend: {e}")
        # Fallback to a basic backend if needed
        from keyring.backends import null
        keyring.set_keyring(null.NullKeyring())

class LicenseManager:
    def __init__(self):
        # Supabase configuration
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            self.logger = self._setup_logger()
            self.logger.error("Supabase credentials not found in environment variables")
            raise ValueError("Supabase credentials not found. Please ensure SUPABASE_URL and SUPABASE_KEY are set.")
            
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Constants
        self.APP_NAME = "Clipbrd"
        self.LICENSE_KEY = "license_key"
        self.LICENSE_DATA = "license_data"
        self.ENCRYPTION_KEY = "encryption_key"
        
        # Setup
        self.logger = self._setup_logger()
        self._ensure_encryption_key()
        self.logger.debug("LicenseManager initialized")

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("LicenseManager")
        logger.setLevel(logging.DEBUG)
        return logger

    def _ensure_encryption_key(self) -> None:
        """Ensure we have an encryption key for storing license data."""
        try:
            key = keyring.get_password(self.APP_NAME, self.ENCRYPTION_KEY)
            if not key:
                self.logger.debug("No encryption key found, generating new one")
                key = Fernet.generate_key().decode()
                keyring.set_password(self.APP_NAME, self.ENCRYPTION_KEY, key)
                self.logger.debug("New encryption key stored successfully")
            else:
                self.logger.debug("Existing encryption key found")
            self.fernet = Fernet(key.encode())
        except Exception as e:
            self.logger.error(f"Error in encryption key setup: {str(e)}")
            raise

    def _encrypt_data(self, data: dict) -> str:
        """Encrypt dictionary data to string."""
        try:
            json_data = json.dumps(data)
            encrypted = self.fernet.encrypt(json_data.encode()).decode()
            self.logger.debug("License data encrypted successfully")
            return encrypted
        except Exception as e:
            self.logger.error(f"Error encrypting data: {str(e)}")
            raise

    def _decrypt_data(self, encrypted_data: str) -> dict:
        """Decrypt string to dictionary data."""
        try:
            decrypted = self.fernet.decrypt(encrypted_data.encode())
            data = json.loads(decrypted)
            self.logger.debug("License data decrypted successfully")
            return data
        except Exception as e:
            self.logger.error(f"Error decrypting license data: {str(e)}")
            return {}

    def get_stored_license(self) -> Tuple[Optional[str], Optional[dict]]:
        """Get stored license key and data from system keyring."""
        try:
            key = keyring.get_password(self.APP_NAME, self.LICENSE_KEY)
            encrypted_data = keyring.get_password(self.APP_NAME, self.LICENSE_DATA)
            
            if key and encrypted_data:
                self.logger.info("Found stored license")
                data = self._decrypt_data(encrypted_data)
                if data:
                    return key, data
                else:
                    self.logger.warning("Failed to decrypt stored license data")
            else:
                self.logger.info("No stored license found")
            return None, None
        except Exception as e:
            self.logger.error(f"Error retrieving stored license: {str(e)}")
            return None, None

    def store_license(self, license_key: str, license_data: dict) -> None:
        """Store license key and data in system keyring."""
        try:
            self.logger.info("Storing license information")
            encrypted_data = self._encrypt_data(license_data)
            keyring.set_password(self.APP_NAME, self.LICENSE_KEY, license_key)
            keyring.set_password(self.APP_NAME, self.LICENSE_DATA, encrypted_data)
            self.logger.info("License stored successfully")
        except Exception as e:
            self.logger.error(f"Error storing license: {str(e)}")
            raise

    def clear_stored_license(self) -> None:
        """Clear stored license information."""
        try:
            self.logger.info("Clearing stored license")
            keyring.delete_password(self.APP_NAME, self.LICENSE_KEY)
            keyring.delete_password(self.APP_NAME, self.LICENSE_DATA)
            self.logger.info("License cleared successfully")
        except keyring.errors.PasswordDeleteError:
            self.logger.debug("No license to clear")
        except Exception as e:
            self.logger.error(f"Error clearing license: {str(e)}")

    def _verify_with_supabase(self, license_key: str) -> Dict[str, Any]:
        """Internal method to verify license with Supabase."""
        try:
            self.logger.info("Verifying license with Supabase")
            
            headers = {
                'apikey': self.supabase_key,
                'Authorization': f'Bearer {self.supabase_key}',
                'Content-Type': 'application/json',
                'Prefer': 'return=minimal'
            }
            
            data = {'input_key': license_key}
            
            response = requests.post(
                f"{self.supabase_url}/rest/v1/rpc/verify_license_key",
                headers=headers,
                json=data
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('is_valid'):
                self.logger.info("License verification successful")
            else:
                self.logger.warning("License verification failed")
            
            return result
            
        except requests.exceptions.RequestException as e:
            self.logger.error("Error in license verification request")
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error(f"Error response status: {e.response.status_code}")
                
                if hasattr(e.response, 'json'):
                    try:
                        error_data = e.response.json()
                        return {
                            'is_valid': False,
                            'message': error_data.get('message', 'Invalid license key'),
                        }
                    except json.JSONDecodeError:
                        self.logger.error("Failed to parse error response")
            return {
                'is_valid': False,
                'message': 'Failed to verify license'
            }

    def activate_license(self, license_key: str) -> Dict[str, Any]:
        """Activate a license key with the server."""
        try:
            self.logger.debug(f"Starting license activation for key: {license_key[:5]}...")
            
            # Verify with Supabase
            verification_result = self._verify_with_supabase(license_key)
            self.logger.debug(f"Verification result: {json.dumps(verification_result, indent=2)}")
            
            if not verification_result.get('is_valid'):
                self.logger.warning("License verification failed")
                return {
                    'status': 'error',
                    'message': verification_result.get('message', 'Invalid license key')
                }

            # Create license data structure
            license_data = {
                'user_id': verification_result.get('user_id'),
                'expires_at': verification_result.get('expires_at'),
                'activated_at': datetime.now(timezone.utc).isoformat(),
                'last_verified': datetime.now(timezone.utc).isoformat()
            }
            
            self.logger.debug(f"Created license data: {json.dumps(license_data, indent=2)}")

            # Store the license locally
            self.store_license(license_key, license_data)
            self.logger.info("License activated and stored successfully")

            return {
                'status': 'success',
                'message': f'License activated successfully. Valid until {verification_result.get("expires_at")}. Please restart the application.',
                'expires_at': verification_result.get('expires_at')
            }

        except Exception as e:
            self.logger.error(f"Error during license activation: {str(e)}")
            try:
                # Try to parse the error as JSON first
                if isinstance(e, str):
                    response_data = json.loads(e)
                else:
                    response_data = json.loads(str(e))
                
                self.logger.debug(f"Parsed response data: {json.dumps(response_data, indent=2)}")
                
                if response_data.get('is_valid') is True:
                    self.logger.debug("Received successful response in JSON format")
                    license_data = {
                        'user_id': response_data.get('user_id'),
                        'expires_at': response_data.get('expires_at'),
                        'activated_at': datetime.now(timezone.utc).isoformat(),
                        'last_verified': datetime.now(timezone.utc).isoformat()
                    }
                    self.logger.debug(f"Created license data from JSON: {json.dumps(license_data, indent=2)}")
                    self.store_license(license_key, license_data)
                    return {
                        'status': 'success',
                        'message': f'License activated successfully. Valid until {response_data.get("expires_at")}',
                        'expires_at': response_data.get('expires_at')
                    }
            except json.JSONDecodeError as json_err:
                self.logger.error(f"Failed to parse response as JSON: {str(json_err)}")
            except Exception as parse_err:
                self.logger.error(f"Error parsing response: {str(parse_err)}")
            
            return {
                'status': 'error',
                'message': f'Activation error: {str(e)}'
            }

    def verify_license(self) -> Dict[str, Any]:
        """Verify the stored license."""
        try:
            # Get stored license
            license_key, license_data = self.get_stored_license()
            if not license_key or not license_data:
                return {
                    'status': 'error',
                    'message': 'No license key stored'
                }

            # Check if license has expired
            expires_at = license_data.get('expires_at')
            if not expires_at:
                return {
                    'status': 'error',
                    'message': 'Invalid license data'
                }

            expiry_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expiry_date:
                self.clear_stored_license()
                return {
                    'status': 'error',
                    'message': 'License has expired'
                }

            # Verify with server
            verification_result = self._verify_with_supabase(license_key)
            
            if not verification_result.get('is_valid'):
                self.clear_stored_license()
                return {
                    'status': 'error',
                    'message': verification_result.get('message', 'License is no longer valid')
                }

            # Update last verified timestamp
            license_data['last_verified'] = datetime.now(timezone.utc).isoformat()
            self.store_license(license_key, license_data)

            return {
                'status': 'success',
                'message': f'License is active. Valid until {expires_at}',
                'expires_at': expires_at
            }

        except Exception as e:
            self.logger.error(f"Error during license verification: {e}")
            return {
                'status': 'error',
                'message': f'Verification error: {str(e)}'
            }

    def is_license_valid(self) -> bool:
        """Quick check if license is valid without server verification."""
        result = self.verify_license()
        return result.get('status') == 'success' 
