# CamosunROV Command Centre

Pilot command centre for underwater ROV.

---

## Developer Setup

### Python setup (Windows)

The command centre runs on **Python 3.14** inside a virtual environment
(`.venv`) in the top directory of this repo. That folder is
**not** committed - each person builds their own from `py_requirements.txt`,
which pins exact package versions so everyone's environment is identical.

#### 1. Install Python 3.14 (once)

3.14 installs alongside any other Python versions you already have; it will not
replace them.

- Recommended: install the Python install manager from python.org, then run
  `py install 3.14`
- Or use the classic python.org 3.14 installer (untick "Add to PATH" if you
  don't want 3.14 to become your default `python`).

Check it is available:

```
py -0
```

This lists the installed Python versions; 3.14 should appear.

#### 2. Create the venv (once, from the repo's top directory)

```
py -3.14 -m venv .venv
```

Use `py -3.14`, not `python` - plain `python` may build the venv with a
different version.

#### 3. Activate it and install dependencies

##### 3a. Activate the venv

```
.venv\Scripts\activate
```

Your prompt should now start with `(.venv)`.

##### 3b. Check the Python version

```
python --version
```

This must print `Python 3.14.x`. If it doesn't, delete the `.venv` folder and
repeat step 2.

##### 3c. Install the dependencies

```
python -m pip install -r py_requirements.txt
```

#### 4. Run the console

```
python rov_console.py
```

#### Day-to-day

- Activate the venv (`.venv\Scripts\activate`) in each new terminal before running.
- After pulling, if `py_requirements.txt` changed, re-run
  `python -m pip install -r py_requirements.txt`.
- Something broken? Delete the `.venv` folder and repeat steps 2-3.
- Adding/upgrading a package: pin the exact version in `py_requirements.txt`,
  install, test, and commit the file.
