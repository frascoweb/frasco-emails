from setuptools import setup, find_packages


setup(
    name='frasco-emails',
    version='0.2.4',
    url='http://github.com/frascoweb/frasco-emails',
    license='MIT',
    author='Maxime Bouroumeau-Fuseau',
    author_email='maxime.bouroumeau@gmail.com',
    description="Emails sending for Frasco",
    packages=find_packages(),
    package_data={
        'frasco_emails': [
            'templates/*.html',
            'templates/layouts/*.html',
            'templates/layouts/MAILGUN_LICENSE',
            'templates/layouts/MAILGUN_README.md']
    },
    zip_safe=False,
    platforms='any',
    install_requires=[
        'frasco',
        'Flask-Mail>=0.9.0',
        'html2text>=2014.7.3',
        'premailer>=2.5.0',
        'Markdown>=2.4.1'
    ]
)
