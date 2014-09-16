from setuptools import setup, find_packages


def desc():
    with open("README.md") as f:
        return f.read()


setup(
    name='frasco-emails',
    version='0.1',
    url='http://github.com/frascoweb/frasco-emails',
    license='MIT',
    author='Maxime Bouroumeau-Fuseau',
    author_email='maxime.bouroumeau@gmail.com',
    description="Emails sending for Frasco",
    long_description=desc(),
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    install_requires=[
        'frasco',
        'Flask-Mail==0.9.0',
        'html2text==2014.7.3',
        'premailer==2.5.0'
    ]
)