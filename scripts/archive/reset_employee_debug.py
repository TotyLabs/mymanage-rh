import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set.")
    exit(1)

engine = create_engine(DATABASE_URL)

TARGET_DNI = "36241305"
TARGET_CUIL = "20362413053"

def reset_employee():
    print(f"Buscando legajo con DNI {TARGET_DNI}...")
    
    with engine.connect() as conn:
        # 1. Obtener IDs
        emp = conn.execute(text("SELECT id FROM employees WHERE dni = :dni OR cuil = :cuil"), 
                           {"dni": TARGET_DNI, "cuil": TARGET_CUIL}).fetchone()
        
        if not emp:
            print("No se encontró el legajo.")
            return

        emp_id = emp.id
        print(f"Legajo encontrado: {emp_id}")

        # 2. Borrar sesiones asociadas a usuarios de este legajo
        user = conn.execute(text("SELECT id FROM users WHERE employee_id = :eid"), {"eid": emp_id}).fetchone()
        if user:
            user_id = user.id
            print(f"Borrando sesiones del usuario {user_id}...")
            conn.execute(text("DELETE FROM user_sessions WHERE user_id = :uid"), {"uid": user_id})
            
            # 3. Borrar el usuario
            print(f"Borrando usuario {user_id}...")
            conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})

        # 4. Resetear estado del legajo
        print("Reseteando estado del legajo a 'pre_registered'...")
        conn.execute(text("""
            UPDATE employees SET 
                status = 'pre_registered', 
                profile_completed = false,
                email = NULL,
                phone = NULL
            WHERE id = :eid
        """), {"eid": emp_id})
        
        conn.commit()
        print("--- Proceso completado con éxito ---")

if __name__ == "__main__":
    reset_employee()
