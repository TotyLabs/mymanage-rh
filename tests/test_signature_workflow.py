import secrets
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to sys.path for direct script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
from modules.digital_signature import accept_signature, DigitalSignatureEngine
from payroll_core import utc_now
# Try to find exactly where EmployeeStatus is defined
try:
    from models.enums import EmployeeStatus
except ImportError:
    try:
        from models.tables import EmployeeStatus
    except ImportError:
        # Fallback if it's missing or named differently
        class EmployeeStatus:
            ACTIVE = "active"

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

@pytest.fixture
def mock_engine():
    engine = MagicMock(spec=DigitalSignatureEngine)
    engine.finalize_db.return_value = {
        "success": True, 
        "receipt_id": "test-receipt-id", 
        "employee_token": "test-emp-token",
        "employee_email": "test@employee.com",
        "period": "2026-01"
    }
    return engine

@patch("modules.digital_signature.get_digital_signature_engine")
@patch("notifications.service.NotificationService.send_signature_pending_notification")
def test_accept_signature_triggers_background_task(mock_send_task, mock_get_engine, mock_db, mock_engine):
    """Verifica que accept_signature dispare la tarea de fondo para el correo."""
    mock_get_engine.return_value = mock_engine
    background_tasks = BackgroundTasks()
    
    # Mock receipt
    mock_receipt = MagicMock()
    mock_receipt.id = "test-receipt-id"
    mock_receipt.processing_signature = True
    mock_db.query().filter().first.return_value = mock_receipt

    res = accept_signature(
        token="valid-token",
        signature_base64="data:image/png;base64,xxxx",
        db=mock_db,
        background_tasks=background_tasks
    )

    assert res["success"] is True
    # Background tasks are executed after the response is sent, 
    # but we can check if it was added to the list.
    assert len(background_tasks.tasks) > 0
    # Ensure the correct task was added
    task_func = background_tasks.tasks[0].func
    assert task_func == mock_send_task

@patch("modules.digital_signature.get_digital_signature_engine")
def test_accept_signature_clears_flag_on_failure(mock_get_engine, mock_db, mock_engine):
    """Verifica que el flag processing_signature se limpie incluso si falla finalize_db."""
    mock_get_engine.return_value = mock_engine
    mock_engine.finalize_db.side_effect = Exception("Finalize failed")
    
    # Mock receipt
    mock_receipt = MagicMock()
    mock_receipt.id = "test-receipt-id"
    mock_receipt.processing_signature = True
    mock_db.query().filter().first.return_value = mock_receipt

    with pytest.raises(Exception, match="Finalize failed"):
        accept_signature(
            token="valid-token",
            signature_base64="data:image/png;base64,xxxx",
            db=mock_db,
            background_tasks=BackgroundTasks()
        )

    # El flag debe haberse limpiado
    assert mock_receipt.processing_signature is False
    mock_db.commit.assert_called()

if __name__ == "__main__":
    # Run tests manually if pytest is failing to provide output
    try:
        from sqlalchemy.orm import Session
        db = MagicMock(spec=Session)
        engine = MagicMock(spec=DigitalSignatureEngine)
        engine.finalize_db.return_value = {"success": True}
        
        print("Running manual test: accept_signature_triggers_background_task...")
        with patch("modules.digital_signature.get_digital_signature_engine", return_value=engine):
            with patch("notifications.service.NotificationService.send_signature_pending_notification") as mock_send:
                bt = BackgroundTasks()
                mock_receipt = MagicMock()
                db.query().filter().first.return_value = mock_receipt
                accept_signature("t", "d", db, bt)
                print("OK: Task added to background" if len(bt.tasks) > 0 else "FAIL: No task")
        
        print("Manual tests completed.")
    except Exception as e:
        print(f"Error during manual test: {e}")
        import traceback
        traceback.print_exc()
