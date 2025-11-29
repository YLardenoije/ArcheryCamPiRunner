"""PTZ (Pan-Tilt-Zoom) controller for ONVIF-compatible cameras."""
import json
import os
from typing import Optional


class PTZController:
    """Manages PTZ control and presets for ONVIF cameras."""
    
    def __init__(self, presets_file: str, camera_host: Optional[str] = None,
                 camera_port: int = 80, username: str = "admin", password: str = "admin"):
        """Initialize PTZ controller.
        
        Args:
            presets_file: Path to JSON file for storing presets
            camera_host: ONVIF camera IP/hostname (optional, can be set later)
            camera_port: ONVIF camera port (default 80)
            username: Camera username for ONVIF authentication
            password: Camera password for ONVIF authentication
        """
        self.presets_file = presets_file
        self.camera_host = camera_host
        self.camera_port = camera_port
        self.username = username
        self.password = password
        
        self._camera = None
        self._ptz_service = None
        self._media_service = None
        self._profile_token = None
        
        # Current PTZ position (cached)
        self._current_position = {"pan": 0.0, "tilt": 0.0, "zoom": 0.0}
        
        # Load presets from file
        self._presets = self._load_presets()
    
    def _load_presets(self) -> dict:
        """Load presets from JSON file."""
        if os.path.exists(self.presets_file):
            try:
                with open(self.presets_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"PTZ: Error loading presets: {e}")
                return {}
        return {}
    
    def _save_presets(self):
        """Save presets to JSON file."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.presets_file), exist_ok=True)
            with open(self.presets_file, 'w') as f:
                json.dump(self._presets, f, indent=2)
            print(f"PTZ: Saved presets to {self.presets_file}")
        except IOError as e:
            print(f"PTZ: Error saving presets: {e}")
            raise
    
    def configure_camera(self, host: str, port: int = 80,
                        username: str = "admin", password: str = "admin"):
        """Configure camera connection settings.
        
        Args:
            host: Camera IP/hostname
            port: ONVIF port (usually 80 or 8080)
            username: Camera username
            password: Camera password
        """
        self.camera_host = host
        self.camera_port = port
        self.username = username
        self.password = password
        # Reset connection
        self._camera = None
        self._ptz_service = None
        self._media_service = None
        self._profile_token = None
        print(f"PTZ: Configured camera at {host}:{port}")
    
    def connect(self) -> bool:
        """Connect to the ONVIF camera.
        
        Returns:
            True if connected successfully, False otherwise
        """
        if not self.camera_host:
            print("PTZ: No camera host configured")
            return False
        
        try:
            from onvif import ONVIFCamera
            
            self._camera = ONVIFCamera(
                self.camera_host,
                self.camera_port,
                self.username,
                self.password
            )
            
            # Get PTZ and media services
            self._media_service = self._camera.create_media_service()
            self._ptz_service = self._camera.create_ptz_service()
            
            # Get the first media profile token
            profiles = self._media_service.GetProfiles()
            if profiles:
                self._profile_token = profiles[0].token
                print(f"PTZ: Connected to camera, profile: {self._profile_token}")
                return True
            else:
                print("PTZ: No media profiles found")
                return False
                
        except ImportError:
            print("PTZ: onvif-zeep library not installed")
            return False
        except Exception as e:
            print(f"PTZ: Failed to connect to camera: {e}")
            self._camera = None
            self._ptz_service = None
            return False
    
    def is_connected(self) -> bool:
        """Check if connected to camera."""
        return self._ptz_service is not None and self._profile_token is not None
    
    def get_position(self) -> dict:
        """Get current PTZ position from camera.
        
        Returns:
            Dict with pan, tilt, zoom values (-1.0 to 1.0 for pan/tilt, 0.0 to 1.0 for zoom)
        """
        if not self.is_connected():
            return self._current_position
        
        try:
            status = self._ptz_service.GetStatus({'ProfileToken': self._profile_token})
            pos = status.Position
            
            self._current_position = {
                "pan": float(pos.PanTilt.x) if pos.PanTilt else 0.0,
                "tilt": float(pos.PanTilt.y) if pos.PanTilt else 0.0,
                "zoom": float(pos.Zoom.x) if pos.Zoom else 0.0
            }
            return self._current_position
        except Exception as e:
            print(f"PTZ: Error getting position: {e}")
            return self._current_position
    
    def absolute_move(self, pan: float, tilt: float, zoom: float) -> bool:
        """Move camera to absolute position.
        
        Args:
            pan: Pan position (-1.0 to 1.0)
            tilt: Tilt position (-1.0 to 1.0)
            zoom: Zoom level (0.0 to 1.0)
            
        Returns:
            True if move command sent successfully
        """
        # Clamp values to valid ranges
        pan = max(-1.0, min(1.0, float(pan)))
        tilt = max(-1.0, min(1.0, float(tilt)))
        zoom = max(0.0, min(1.0, float(zoom)))
        
        if not self.is_connected():
            print(f"PTZ: Not connected, caching position: pan={pan}, tilt={tilt}, zoom={zoom}")
            self._current_position = {"pan": pan, "tilt": tilt, "zoom": zoom}
            return True
        
        try:
            # Build the request
            request = self._ptz_service.create_type('AbsoluteMove')
            request.ProfileToken = self._profile_token
            
            # Set position
            request.Position = {
                'PanTilt': {'x': pan, 'y': tilt},
                'Zoom': {'x': zoom}
            }
            
            self._ptz_service.AbsoluteMove(request)
            self._current_position = {"pan": pan, "tilt": tilt, "zoom": zoom}
            print(f"PTZ: Moved to pan={pan}, tilt={tilt}, zoom={zoom}")
            return True
            
        except Exception as e:
            print(f"PTZ: Error moving camera: {e}")
            return False
    
    def stop(self) -> bool:
        """Stop any ongoing PTZ movement.
        
        Returns:
            True if stop command sent successfully
        """
        if not self.is_connected():
            return True
        
        try:
            request = self._ptz_service.create_type('Stop')
            request.ProfileToken = self._profile_token
            request.PanTilt = True
            request.Zoom = True
            self._ptz_service.Stop(request)
            print("PTZ: Movement stopped")
            return True
        except Exception as e:
            print(f"PTZ: Error stopping movement: {e}")
            return False
    
    def list_presets(self) -> dict:
        """Get all saved presets.
        
        Returns:
            Dict of preset name -> position dict
        """
        return self._presets.copy()
    
    def save_preset(self, name: str, pan: float, tilt: float, zoom: float) -> bool:
        """Save a PTZ position as a preset.
        
        Args:
            name: Preset name (alphanumeric, underscores, hyphens)
            pan: Pan position (-1.0 to 1.0)
            tilt: Tilt position (-1.0 to 1.0)
            zoom: Zoom level (0.0 to 1.0)
            
        Returns:
            True if saved successfully
        """
        # Validate name
        if not name or not name.replace('_', '').replace('-', '').replace(' ', '').isalnum():
            print(f"PTZ: Invalid preset name: {name}")
            return False
        
        # Clamp values
        pan = max(-1.0, min(1.0, float(pan)))
        tilt = max(-1.0, min(1.0, float(tilt)))
        zoom = max(0.0, min(1.0, float(zoom)))
        
        self._presets[name] = {
            "pan": pan,
            "tilt": tilt,
            "zoom": zoom
        }
        
        try:
            self._save_presets()
            print(f"PTZ: Saved preset '{name}': pan={pan}, tilt={tilt}, zoom={zoom}")
            return True
        except Exception as e:
            print(f"PTZ: Failed to save preset: {e}")
            return False
    
    def delete_preset(self, name: str) -> bool:
        """Delete a saved preset.
        
        Args:
            name: Preset name to delete
            
        Returns:
            True if deleted successfully
        """
        if name not in self._presets:
            print(f"PTZ: Preset '{name}' not found")
            return False
        
        del self._presets[name]
        
        try:
            self._save_presets()
            print(f"PTZ: Deleted preset '{name}'")
            return True
        except Exception as e:
            print(f"PTZ: Failed to delete preset: {e}")
            return False
    
    def goto_preset(self, name: str) -> bool:
        """Move camera to a saved preset position.
        
        Args:
            name: Preset name
            
        Returns:
            True if move initiated successfully
        """
        if name not in self._presets:
            print(f"PTZ: Preset '{name}' not found")
            return False
        
        preset = self._presets[name]
        return self.absolute_move(preset["pan"], preset["tilt"], preset["zoom"])
    
    def get_preset(self, name: str) -> Optional[dict]:
        """Get a specific preset by name.
        
        Args:
            name: Preset name
            
        Returns:
            Preset position dict or None if not found
        """
        return self._presets.get(name)
