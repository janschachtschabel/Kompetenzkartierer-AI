"""The models and rules of Curriculum-Kern 1.0 the app keeps: plain Python, no framework.

The API, the jobs, the database layer and the exports import the domain; the domain imports none
of them, only the standard library and ``regex`` (Gesamtplan §6.5) - tests/domain/test_imports.py
checks every module.
"""
