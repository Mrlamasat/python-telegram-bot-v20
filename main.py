diff --git a/main.py b/main.py
index c0697b34c651f318f7240fff4e7ef1f266646b89..a056ca0f7e8452fc96690f655a8e26ffbaf1f78b 100644
--- a/main.py
+++ b/main.py
@@ -1,27 +1,50 @@
 from pyrogram import Client, filters
-from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID
-from handlers import handle_video, handle_poster, handle_ep_number, handle_quality
-from commands import start_handler, callback_watch
+from pyrogram.handlers import CallbackQueryHandler, MessageHandler
 
-app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
+from commands import callback_watch, start_handler
+from config import API_HASH, API_ID, BOT_TOKEN, CHANNEL_ID
+from handlers import handle_ep_number, handle_poster, handle_quality, handle_video
 
-# استقبال الفيديو
-app.add_handler(filters.chat(CHANNEL_ID) & (filters.video | filters.document), handle_video)
 
-# استقبال البوستر
-app.add_handler(filters.chat(CHANNEL_ID) & filters.photo, handle_poster)
+def create_app() -> Client:
+    app = Client("BottemoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
 
-# رقم الحلقة
-app.add_handler(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]), handle_ep_number)
+    # استقبال الفيديو
+    app.add_handler(MessageHandler(handle_video, filters.chat(CHANNEL_ID) & (filters.video | filters.document)))
 
-# الجودة
-app.add_handler(filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]), handle_quality)
+    # استقبال البوستر
+    app.add_handler(MessageHandler(handle_poster, filters.chat(CHANNEL_ID) & filters.photo))
 
-# أوامر البوت
-app.add_handler(filters.command("start") & filters.private, start_handler)
+    # رقم الحلقة
+    app.add_handler(
+        MessageHandler(
+            handle_ep_number,
+            filters.chat(CHANNEL_ID) & filters.text & filters.regex(r"^\d+$") & ~filters.command(["start"]),
+        )
+    )
 
-# الضغط على أي حلقة
-app.add_handler(filters.callback_query(filters.regex(r"^watch_")), callback_watch)
+    # الجودة
+    app.add_handler(
+        MessageHandler(
+            handle_quality,
+            filters.chat(CHANNEL_ID) & filters.text & ~filters.command(["start"]),
+        )
+    )
 
-print("✅ البوت جاهز ويعمل الآن!")
-app.run()
+    # أوامر البوت
+    app.add_handler(MessageHandler(start_handler, filters.command("start") & filters.private))
+
+    # الضغط على أي حلقة
+    app.add_handler(CallbackQueryHandler(callback_watch, filters.regex(r"^watch_")))
+
+    return app
+
+
+def run_bot() -> None:
+    app = create_app()
+    print("✅ البوت جاهز ويعمل الآن!")
+    app.run()
+
+
+if __name__ == "__main__":
+    run_bot()
