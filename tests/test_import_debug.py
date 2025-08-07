# test_import_debug.py
import sys
import os

print("=== DEBUG IMPORT ===")
print(f"CWD: {os.getcwd()}")

# Tester chaque étape
sys.path.insert(0, 'src')
print(f"Path ajouté: src")

try:
    import data_import
    print("✅ import data_import OK")
    print(f"   Contenu: {dir(data_import)}")
    
    import data_import.import_manager
    print("✅ import data_import.import_manager OK")
    
    from data_import.import_manager import ImportManager
    print("✅ ImportManager importé avec succès!")
    
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()