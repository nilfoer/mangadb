import setuptools

from manga_db import VERSION

with open("README.md", "r", encoding="UTF-8") as fh:
    long_description = fh.read()


setuptools.setup(
    name="MangaDB",
    version=VERSION,
    description="Organize your manga reading habits",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nilfoer/mangadb",
    author="nilfoer",
    author_email="",
    license="MIT",
    keywords="manga database",
    packages=setuptools.find_packages(exclude=['tests*']),
    python_requires='>=3.8',
    install_requires=["pyperclip>=1.5.25,<=1.7.0",
                      "beautifulsoup4>=4.5.3,<=4.6.3",
                      "flask>=0.12,<=1.0.2",
                      "pillow>=5.3.0,<=8.1.0"],
    tests_require=['pytest'],
    # non-python data that should be included in the pkg
    # mapping from package name to a list of relative path names that should be
    # copied into the package
    # package_data works for bdist and not sdist. However, MANIFEST.in works
    # for sdist, but not for bdist! Therefore, the best I have been able to
    # come up with is to include both package_data and MANIFEST.in in order to
    # accommodate both bdist and sdist
    package_data={
        # add static and templates folder to manga_db.webGUI package
        # folder path is relative to path of that package
        # no recursive include (but i can use custom python code here)
        "manga_db.webGUI": ["static/*", "templates/*", "templates/auth/*", "static/webfonts/*"],
        "manga_db": ["extractor/*.py", "db/migrations/*.py"]
        },
    entry_points={
        'console_scripts': [
            # linking the executable manga_db here to running the python function cli.main
            'manga_db=manga_db.cli:main',
        ]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
