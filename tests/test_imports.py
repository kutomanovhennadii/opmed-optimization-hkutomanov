def test_imports():
    import opmed
    import opmed.dataloader
    import opmed.solver_core

    # проверяем, что модули реально загрузились
    assert all([opmed, opmed.dataloader, opmed.solver_core])
