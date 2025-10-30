#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import json
import time
import xbmc


class Cache:
    """Simple file-based cache"""
    
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir)
            except:
                pass
    
    def get(self, key, max_age=86400):
        """Get cached value"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{key}.json")
            
            if not os.path.exists(cache_file):
                return None
            
            # Check age
            file_age = time.time() - os.path.getmtime(cache_file)
            if file_age > max_age:
                os.remove(cache_file)
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            xbmc.log(f'Cache get error: {str(e)}', xbmc.LOGERROR)
            return None
    
    def set(self, key, value):
        """Set cached value"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{key}.json")
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(value, f)
            
            return True
            
        except Exception as e:
            xbmc.log(f'Cache set error: {str(e)}', xbmc.LOGERROR)
            return False
    
    def clear(self):
        """Clear all cache"""
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    os.remove(os.path.join(self.cache_dir, filename))
            return True
        except Exception as e:
            xbmc.log(f'Cache clear error: {str(e)}', xbmc.LOGERROR)
            return False