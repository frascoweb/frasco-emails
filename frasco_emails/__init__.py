from frasco import Feature, action, current_context, OptionMissingError, translate, copy_extra_feature_options
from jinja_macro_tags import MacroLoader, MacroRegistry
from frasco.utils import parse_yaml_frontmatter
from frasco.expression import compile_expr, eval_expr
from flask_mail import Mail, Message, email_dispatched, Attachment, force_text
from jinja2 import ChoiceLoader, FileSystemLoader, PackageLoader
from contextlib import contextmanager
import html2text
import premailer
import os
import datetime
import re



_url_regexp = re.compile(r'(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)')
def clickable_links(text):
    return _url_regexp.sub(r'<a href="\1">\1</a>', text)


class EmailsFeature(Feature):
    """Send emails using SMTP
    """
    name = "emails"
    defaults = {"default_layout": "layout.html",
                "default_template_vars": {},
                "inline_css": False,
                "auto_render_missing_content_type": True,
                "log_messages": None, # default is app.testing
                "dump_logged_messages": True,
                "dumped_messages_folder": "email_logs"}

    def init_app(self, app):
        copy_extra_feature_options(self, app.config, "MAIL_")

        self.client = Mail(app)
        self.connection = None

        self.templates_loader = [FileSystemLoader(os.path.join(app.root_path, "emails"))]
        layout_loader = PackageLoader(__name__, "templates")
        loader = ChoiceLoader([ChoiceLoader(self.templates_loader), layout_loader])
        self.jinja_env = app.jinja_env.overlay(loader=MacroLoader(loader))
        self.jinja_env.macros = MacroRegistry(self.jinja_env) # the overlay methods does not call the constructor of extensions
        self.jinja_env.macros.register_from_template("layouts/macros.html")
        self.jinja_env.default_layout = self.options["default_layout"]
        self.jinja_env.filters['clickable_links'] = clickable_links

        if (self.options["log_messages"] is not None and self.options["log_messages"]) or \
            (self.options["log_messages"] is None and app.testing):
            email_dispatched.connect(self.log_message)

    def add_template_folder(self, path):
        self.templates_loader.append(FileSystemLoader(path))

    def add_templates_from_package(self, pkg_name, pkg_path="emails"):
        self.templates_loader.append(PackageLoader(pkg_name, pkg_path))

    def render_message(self, template_filename, **vars):
        text_body = None
        html_body = None
        vars = dict(self.options["default_template_vars"], **vars)

        source, _, __ = self.jinja_env.loader.get_source(self.jinja_env, template_filename)
        frontmatter, source = parse_yaml_frontmatter(source)
        if frontmatter:
            vars = dict(frontmatter, **vars)
        frontmatter = eval_expr(compile_expr(frontmatter), vars)

        filename, ext = os.path.splitext(template_filename)
        templates = [("%s.%s" % (filename, e), e) for e in ext[1:].split(",")]
        for filename, ext in templates:
            rendered = self.jinja_env.get_template(filename).render(**vars)
            if ext == "html":
                html_body = rendered
                if self.options["auto_render_missing_content_type"]:
                    text_body = html2text.html2text(html_body)
            else:
                text_body = rendered
                if self.options["auto_render_missing_content_type"]:
                    html_body = self.jinja_env.get_template("layouts/text.html").render(
                        text_body=text_body, **vars)

        if html_body and self.options["inline_css"]:
            html_body = premailer.transform(html_body)

        return (frontmatter, text_body, html_body)

    @action("create_email_message", as_="email_message")
    def create_message(self, to, tpl, **vars):
        recipients = to if isinstance(to, (list, tuple)) else [to]
        frontmatter, text_body, html_body = self.render_message(tpl, **vars)

        kwargs = {}
        for k in ('subject', 'sender', 'cc', 'bcc', 'attachments', 'reply_to', 'send_date', 'charset', 'extra_headers'):
            if k in vars:
                kwargs[k] = vars[k]
            elif k in frontmatter:
                kwargs[k] = frontmatter[k]
        kwargs["date"] = kwargs.pop("send_date", None)

        if not kwargs.get("subject"):
            raise OptionMissingError("Missing subject for email with template '%s'" % tpl)
        subject = translate(kwargs.pop("subject"))
        attachments = kwargs.pop("attachments", None)

        msg = Message(recipients=recipients, subject=subject, body=text_body, html=html_body, **kwargs)
        msg.template = tpl

        if attachments:
            for attachment in attachments:
                if isinstance(attachment, Attachment):
                    msg.attachments.append(attachment)
                elif isinstance(attachment, dict):
                    msg.attach(**attachment)
                else:
                    msg.attach(attachment)

        current_context.data.mail_message = msg
        return msg

    @action("add_email_attachment", default_option="filename")
    def add_attachment(self, filename, msg=None, **kwargs):
        msg = msg or current_context.data.mail_message
        msg.attach(filename, **kwargs)

    @action("start_bulk_emails")
    def start_bulk(self):
        self.connection = self.client.connect()
        # simulate entering a with context
        # (flask-mail does not provide a way to connect otherwise)
        self.connection.__enter__()

    @action("stop_bulk_emails")
    def stop_bulk(self):
        self.connection.__exit__(None, None, None) # see start_bulk()
        self.connection = None

    @contextmanager
    def bulk(self):
        self.start_bulk()
        try:
            yield self
        finally:
            self.stop_bulk()

    @action("send_email")
    def send(self, to=None, tpl=None, **kwargs):
        msg = None
        if isinstance(to, Message):
            msg = to
        elif to is None and "mail_message" in current_context.data:
            msg = current_context.data.mail_message
        else:
            if not to:
                raise OptionMissingError("A recipient must be provided when sending an email")
            if not tpl:
                raise OptionMissingError("A template must be provided when sending an email")
            msg = self.create_message(to, tpl, **kwargs)

        if self.connection:
            self.connection.send(msg)
        else:
            self.client.send(msg)

    def log_message(self, message, app):
        app.logger.debug("Email %s sent to %s as \"%s\"" % (message.template, message.recipients, message.subject))
        if self.options["dump_logged_messages"]:
            path = os.path.join(app.root_path, self.options["dumped_messages_folder"])
            if not os.path.exists(path):
                os.mkdir(path, 0777)
            filename = os.path.join(path, "-".join([
                datetime.datetime.now().isoformat("-"),
                os.path.splitext(message.template)[0].replace("/", "_"),
                "-".join(message.recipients)]))
            if message.body:
                with open(filename + ".txt", "w") as f:
                    f.write(message.body)
            if message.html:
                with open(filename + ".html", "w") as f:
                    f.write(message.html)