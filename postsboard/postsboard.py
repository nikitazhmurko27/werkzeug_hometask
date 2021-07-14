import operator
import os
import redis
import json
from werkzeug.urls import url_parse
from werkzeug.wrappers import Request, Response
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.middleware.shared_data import SharedDataMiddleware
from werkzeug.utils import redirect
from jinja2 import Environment, FileSystemLoader
from datetime import datetime


class PostsBoard(object):

    def __init__(self, config):
        self.redis = redis.Redis(config['redis_host'], config['redis_port'])
        template_path = os.path.join(os.path.dirname(__file__), 'templates')
        self.jinja_env = Environment(loader=FileSystemLoader(template_path),
                                     autoescape=True)
        self.url_map = Map([
            Rule('/', endpoint='homepage'),
            Rule('/post/<post_id>', endpoint='single_post'),
            Rule('/create', endpoint='create_post')
        ])

    def _read_postsboard_data(self,):
        with open("postsboard.json") as json_file:
            json_object = json.load(json_file)
            json_file.close()
            return json_object

    def _get_post_by_id(self, post_id):
        data = self._read_postsboard_data()
        posts = data['posts']
        post_content = ''
        for post in posts:
            if post['id'] == int(post_id):
                post_content = post
                break
        return post_content

    def _add_post(self, post):
        data = self._read_postsboard_data()
        data['posts'] += list(post)
        with open('postsboard.json', 'w') as f:
            json.dump(data, f)

    def _get_post_comments(self, post_id):
        data = self._read_postsboard_data()
        comments = data['comments']
        post_comments = []
        for comment in comments:
            if comment['post_id'] != int(post_id):
                continue
            post_comments.append(comment)
        post_comments.sort(key=operator.itemgetter('created_at'), reverse=True)
        return post_comments

    def _add_comment(self, comment):
        data = self._read_postsboard_data()
        data['comments'] += list(comment)
        with open('postsboard.json', 'w') as f:
            json.dump(data, f)

    def render_template(self, template_name, **context):
        t = self.jinja_env.get_template(template_name)
        return Response(t.render(context), mimetype='text/html')

    def dispatch_request(self, request):
        adapter = self.url_map.bind_to_environ(request.environ)
        try:
            endpoint, values = adapter.match()
            return getattr(self, f'on_{endpoint}')(request, **values)
        except HTTPException as e:
            return e

    def on_homepage(self, request):
        data = self._read_postsboard_data()
        posts = data['posts']
        posts.sort(key=operator.itemgetter('created_at'), reverse=True)
        return self.render_template("homepage.html", posts=posts)

    def on_single_post(self, request, post_id):
        post_content = self._get_post_by_id(post_id)
        post_comments = self._get_post_comments(post_id)
        if request.method == "GET":
            return self.render_template("single_post.html", post=post_content, comments=post_comments)
        if request.method == "POST":
            errors = []
            if len(request.form["author"]) > 100:
                errors.append("The author field should be less than 100 symbols")
            if len(request.form["comment"]) > 200:
                errors.append("The comment field should be less than 200 symbols")
            if len(errors) > 0:
                return self.render_template("single_post.html",
                                            post=post_content,
                                            comments=post_comments,
                                            author=request.form["author"],
                                            comment=request.form["comment"],
                                            errors=errors)
            data = self._read_postsboard_data()
            comments = data['comments']
            now = datetime.now()
            new_comment = ({
                "id": len(comments) + 1,
                "post_id": int(post_id),
                "text": request.form["comment"],
                "author": request.form["author"],
                "created_at": now.strftime("%d/%m/%Y %H:%M")
            },)
            self._add_comment(new_comment)
            return redirect(f'/post/{post_id}')
        return Response(f"post_id = {post_id}")

    def on_create_post(self, request):
        if request.method == "GET":
            return self.render_template("create_post.html")
        if request.method == "POST":
            errors = []
            if len(request.form["title"]) > 100:
                errors.append("The title field should be less than 100 symbols")
            if len(request.form["content"]) > 1000:
                errors.append("The content field should be less than 1000 symbols")
            if len(request.form["author"]) > 100:
                errors.append("The author field should be less than 100 symbols")
            if len(errors) > 0:
                return self.render_template("create_post.html",
                                            author=request.form["author"],
                                            title=request.form["title"],
                                            content=request.form["content"],
                                            errors=errors)
            now = datetime.now()
            data = self._read_postsboard_data()
            posts = data['posts']
            new_post = ({
                "id": len(posts) + 1,
                "title": request.form["title"],
                "text": request.form["content"],
                "author": request.form["author"],
                "created_at": now.strftime("%d/%m/%Y %H:%M")
            },)
            self._add_post(new_post)
            return redirect('/')

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        response = self.dispatch_request(request)
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)


def create_app(redis_host='localhost', redis_port=6379, with_static=True):
    app = PostsBoard({
        'redis_host': redis_host,
        'redis_port': redis_port
    })
    if with_static:
        app.wsgi_app = SharedDataMiddleware(app.wsgi_app, {
            '/static':  os.path.join(os.path.dirname(__file__), 'static')
        })
    return app


if __name__ == '__main__':
    from werkzeug.serving import run_simple
    app = create_app()
    run_simple('127.0.0.1', 5000, app, use_debugger=True, use_reloader=True)
