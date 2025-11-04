def test_imports():
    """
    @brief
    Verifies that all core Opmed modules are importable.

    @details
    Ensures package structure integrity and confirms that
    opmed, opmed.dataloader, and opmed.solver_core are accessible
    without import errors.
    """
    import opmed
    import opmed.dataloader
    import opmed.solver_core

    # --- Assert ---
    # Confirm that modules were successfully imported and resolved
    assert all([opmed, opmed.dataloader, opmed.solver_core])
