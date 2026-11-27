# Contributing

Thank you for your interest in this project.

## Report a problem

Open an issue. Include these items:

1. The command you ran.
2. The input type, GPX or FIT.
3. The Python version and the Pillow version.
4. What you expected and what you got.

Do not attach a GPX or FIT file with private data. Make a small test file instead.

## Send a change

1. Fork the repository.
2. Create a branch from `main`.
3. Make your change.
4. Run the checks below.
5. Open a pull request against `main`.

Keep one pull request for one change.

## Checks

Install the dependencies:

```
pip install Pillow fitparse
```

Run these commands from the repository root:

```
python -m py_compile running-card.py examples/make_examples.py
python running-card.py examples/demo.gpx --output /tmp/demo.png
python running-card.py examples/dagersheim-waldlauf.fit --output /tmp/race.png
```

Open the two PNG files and look at them.

GitHub runs the same steps on every pull request. A pull request needs a
passing `smoke` check before a merge.

## Rules for a change

1. Keep the tool in one script. Do not add a package.
2. Add a dependency only when the Python standard library cannot do the task.
   Document the dependency in the README.
3. Update the README when an option or the output changes.
4. Run `python examples/make_examples.py` when the card output changes, and
   commit the new example files.
5. Keep the code style of the file. Keep the comments short and useful.
6. Write the commit message in the imperative, for example
   `Add the outline option`.

## Licence

The MIT licence covers your contribution. See `LICENSE`.
