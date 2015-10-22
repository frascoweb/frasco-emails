# Frasco-Emails

Frasco features to send templated emails using [Flask-Mail](https://pythonhosted.org/flask-mail/).

## Installation

    pip install frasco-emails

## Setup

Feature name: emails

Options:

 - *default_layout*: name of the default layout for your email templates
 - *default_template_vars*: dict of template vars
 - *inline_css*: whether to automatically inline css rules using
   [premailer](https://pypi.python.org/pypi/premailer) (default: false)
 - *auto_render_missing_content_type*: whether to automatically render the
   text version when only the html is provided and the opposite when only
   the text is provided. (default: true)
 - *log_messages*: whether to add a log entry when an email is sent
   (default: same as app.testing)
 - *dump_logged_messages*: whether to dump sent emails as files when
   *log_messages* is true.
 - *dumped_messages_folder*: folder where to dump the emails (default: email_logs)

Plus all the options of Flask-Mail.

For licensing reason, *html2text* is not included in the dependencies. It is needed to convert html emails to text in the case *auto_render_missing_content_type* is set to true. Install it using pip if you plan on converting html emails to text:

    $ pip install html2text

## Email templates

Templates for your emails are located in the *emails* folder. Templates can
either be text files (with the .txt extension) or html files (with the .html extension).
Both of them can have a YAML front-matter which can be used to define template
vars as well as options for your email message. Available options are:

 - *subject*
 - *sender*
 - *cc*
 - *bcc*
 - *attachments*: a list where items can either be:
   - a filename
   - a dicts of keyword arguments for `flaskext.mail.Message.attach`
 - *reply_to*
 - *send_date*
 - *charset*
 - *extra_headers*

These options are in fact keyword arguments for `flaskext.mail.Message.__init__`.

    ---
    subject: Welcome to example.com
    ---
    Welcome {{ firstname }},
    Thanks for signing up!

When sending your email, the template filename is relative to the emails folder.
So if you have created a template in *emails/welcome.txt*, you can reference it
using *welcome.txt*. Because of the *txt* extension, this template will be used
for text plain text mime type of your message. If instead of *txt*, the file
extension was *html*, the template would be used for the html mime type of your
message.

If you have created *welcome.txt* and *welcome.html* and want to use both, thus
sending a multipart mime message with text and html content, you can do it by
providing multiple file extensions separated by a comma: *welcome.txt,html*.

However, Frasco-Emails has a great feature which automatically converts one type
to the other to always provide a text and an html mime type. In the case where
just the text content is provided, this will be converted to html using the
default layout. In the case where just the html content is provided, the html
will be converted to text using [html2text](https://github.com/aaronsw/html2text).

Note that we do not recommend using the html to text convertion as the result
is not guaranteed to be perfect.

## HTML emails

HTML emails are notoriously annoying to produce due to the variety of email clients
and their limited html processors. Fortunately, a default layout based on the
[transactional email templates](http://blog.mailgun.com/transactional-html-email-templates/)
created by Mailgun is provided.

These layouts are available in three variants:

 - *layouts/base.html*: for standard email messages (which is the default layout)
 - *layouts/alert.html*: for alerts
 - *layouts/invoice.html* for invoices

The base templates has the following blocks which you can override:

 - *title*: inside the `<title>` html tag
 - *header*
 - *content_block*: main content block which contains these subblocks:
   - *content*: to directly add text content
   - *signature*
 - *footer*

While the *title* block is straightforward, the other are actually located inside
tables. To facilitate adding content to your email, these macros are available:

 - `mail_content(center=False)`: creates the block wrapping your content for your email
 - `mail_block(center=False)`: a content block
 - `mail_signature(author)`: a content block for signature
 - `mail_action_btn(label, url)`: a content block containing a single action button
 - `mail_alert(label="good")`: to use in the header block for alert emails. *label* can
   be one of: warning, bad, good
 - `mail_link(url, label=None)`: to add an html link in your text with the style already
   inlined. can be used as a call block.

As an example, let's create an email validation message:

    ---
    subject: Validate your email
    ---
    {% use_layout %}
    {% block content_block %}
      <{ mail_content }>
        <{ mail_block }>
          Thank you for signing up to our great website. Take a minute
          to validate your email
        </{ mail_block }>
        <{ mail_action_btn label="Validate your email" url=url_for('validate_email', _external=True) }/>
        <{ mail_signature author="the team at example.com" }/>
      </{ mail_content }>
    {% endblock %}

When using the *layouts/alert.html* template, you can configure the way the header appears
using two variables:

 - *alert_label*: the label of your alert (see `mail_alert` macro) (default: good)
 - *alert_message*: the title of your alert (default: same as subject)

When using the *layouts/invoice.html* template, you'll need to provide these variables:

 - *invoice_header*: text to show before the details
 - *invoice_items*: a list where each item is a tuple of the form (label, amount).
 - *invoice_currency*: the currency symbol (default: dollar sign)
 - *invoice_total*: total amount

New template blocks are also available (these blocks are located inside the *content_block*)

 - *before_invoice*
 - *after_invoice*

## Actions

### send\_email

Send a templated email

Options:

 - *to*: the recipient's email address
 - *tpl*: the template name
 - other options will be available as template variables

### create\_email\_message

Create an email message without sendint it.

Options:

 - *to*: the recipient's email address
 - *tpl*: the template name
 - other options will be available as template variables

Example:

    ---
    url: /something
    actions:
      - create_email_message: { to: example@example.com, tpl: welcome.txt }
      - add_email_attachment: "welcome_guide.pdf"
      - send_email

### add\_email\_attachment

Adds an email attachment to a message created using *create_email_message*.

Options:

 - *filename*
 - other options are forwarded to `flaskext.mail.Message.attach`

### start\_bulk\_emails

Call this before sending multiple emails at the same time

### stop\_bulk\_emails

Call this once all emails have been sent
