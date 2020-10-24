PRAGMA foreign_keys=off;
BEGIN TRANSACTION;
CREATE TABLE Artist(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL,
                    favorite INTEGER NOT NULL DEFAULT 0
                );
CREATE TABLE "BookArtist" (
	"book_id"	INTEGER NOT NULL,
	"artist_id"	INTEGER NOT NULL,
	FOREIGN KEY("book_id") REFERENCES "Books"("id") ON DELETE CASCADE,
	PRIMARY KEY("book_id","artist_id"),
	FOREIGN KEY("artist_id") REFERENCES "Artist"("id") ON DELETE CASCADE
);
CREATE TABLE "BookCategory" (
	"book_id"	INTEGER NOT NULL,
	"category_id"	INTEGER NOT NULL,
	FOREIGN KEY("book_id") REFERENCES "Books"("id") ON DELETE CASCADE,
	PRIMARY KEY("book_id","category_id"),
	FOREIGN KEY("category_id") REFERENCES "Category"("id") ON DELETE CASCADE
);
CREATE TABLE "BookCharacter" (
	"book_id"	INTEGER NOT NULL,
	"character_id"	INTEGER NOT NULL,
	FOREIGN KEY("character_id") REFERENCES "Character"("id") ON DELETE CASCADE,
	FOREIGN KEY("book_id") REFERENCES "Books"("id") ON DELETE CASCADE,
	PRIMARY KEY("book_id","character_id")
);
CREATE TABLE "BookCollection" (
	"book_id"	INTEGER NOT NULL,
	"collection_id"	INTEGER NOT NULL,
	FOREIGN KEY("book_id") REFERENCES "Books"("id") ON DELETE CASCADE,
	PRIMARY KEY("book_id","collection_id"),
	FOREIGN KEY("collection_id") REFERENCES "Collection"("id") ON DELETE CASCADE
);
CREATE TABLE "BookGroups" (
	"book_id"	INTEGER NOT NULL,
	"group_id"	INTEGER NOT NULL,
	FOREIGN KEY("book_id") REFERENCES "Books"("id") ON DELETE CASCADE,
	PRIMARY KEY("book_id","group_id"),
	FOREIGN KEY("group_id") REFERENCES "Groups"("id") ON DELETE CASCADE
);
CREATE TABLE "BookList" (
	"book_id"	INTEGER NOT NULL,
	"list_id"	INTEGER NOT NULL,
	FOREIGN KEY("book_id") REFERENCES "Books"("id") ON DELETE CASCADE,
	PRIMARY KEY("book_id","list_id"),
	FOREIGN KEY("list_id") REFERENCES "List"("id") ON DELETE CASCADE
);
CREATE TABLE "BookParody" (
	"book_id"	INTEGER NOT NULL,
	"parody_id"	INTEGER NOT NULL,
	FOREIGN KEY("book_id") REFERENCES "Books"("id") ON DELETE CASCADE,
	PRIMARY KEY("book_id","parody_id"),
	FOREIGN KEY("parody_id") REFERENCES "Parody"("id") ON DELETE CASCADE
);
CREATE TABLE "BookTag" (
	"book_id"	INTEGER NOT NULL,
	"tag_id"	INTEGER NOT NULL,
	FOREIGN KEY("book_id") REFERENCES "Books"("id") ON DELETE CASCADE,
	PRIMARY KEY("book_id","tag_id"),
	FOREIGN KEY("tag_id") REFERENCES "Tag"("id") ON DELETE CASCADE
);
CREATE TABLE Books(
                        id INTEGER PRIMARY KEY ASC,
                        title_eng TEXT,
                        title_foreign TEXT,
                        language_id INTEGER NOT NULL,
                        pages INTEGER NOT NULL,
                        status_id INTERGER NOT NULL,
                        read_status INTEGER,
                        my_rating REAL,
                        note TEXT,
                        last_change DATE NOT NULL,
                        favorite INTEGER NOT NULL,
                        FOREIGN KEY (language_id) REFERENCES Languages(id)
                           ON DELETE RESTRICT,
                        FOREIGN KEY (status_id) REFERENCES Status(id)
                           ON DELETE RESTRICT
                    );
CREATE TABLE Category(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE Censorship (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE Character(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE Collection(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE ExternalInfo(
                        id INTEGER PRIMARY KEY ASC,
                        book_id INTEGER NOT NULL,
                        id_onpage INTEGER NOT NULL,
                        imported_from INTEGER NOT NULL,
                        upload_date DATE NOT NULL,
                        uploader TEXT,
                        censor_id INTEGER NOT NULL,
                        rating REAL,
                        ratings INTEGER, -- number of users that rated the book
                        favorites INTEGER,
                        downloaded INTEGER NOT NULL,
                        last_update DATE NOT NULL,
                        outdated INTEGER NOT NULL,
                        FOREIGN KEY (book_id) REFERENCES Books(id)
                           ON DELETE CASCADE,
                        FOREIGN KEY (imported_from) REFERENCES Sites(id)
                           ON DELETE RESTRICT,
                        FOREIGN KEY (censor_id) REFERENCES Censorship(id)
                           ON DELETE RESTRICT
                    );
CREATE TABLE Groups(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE Languages (
                     id INTEGER PRIMARY KEY ASC,
                     name TEXT UNIQUE NOT NULL
                );
CREATE TABLE List(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE MDB_Version (
    version_id INTEGER PRIMARY KEY ASC,
    dirty INTEGER NOT NULL
    );
CREATE TABLE Parody(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE Sites (
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE Status(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE Tag(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
INSERT INTO "Artist" VALUES
(1,'Ayano Naoto',0),
(2,'SAKULA',0),
(3,'Fan no Hitori',0),
(4,'Jirou',0),
(5,'Kirisaki Byakko',0),
(6,'Korotsuke',0),
(7,'DATE',0),
(8,'ryuno',0),
(9,'Tanabe Kyou',0),
(10,'Yamamoto Zenzen',0),
(11,'Taniguchi-san',0),
(12,'Kaneda Asou',0),
(13,'Fei',0),
(14,'Sirokuma',0),
(15,'bariun',0),
(16,'Tawara Hiryuu',0);
INSERT INTO "BookArtist" VALUES
(1,1),
(2,2),
(3,3),
(4,4),
(5,5),
(6,6),
(7,7),
(8,8),
(9,9),
(10,10),
(11,11),
(12,12),
(13,13),
(14,3),
(15,14),
(16,15),
(17,16);
INSERT INTO "BookCategory" VALUES
(1,1),
(2,1),
(3,2),
(4,2),
(5,1),
(6,1),
(7,1),
(8,2),
(9,2),
(10,1),
(11,2),
(12,1),
(13,1),
(14,2),
(15,2),
(16,1),
(17,2);
INSERT INTO "BookCharacter" VALUES
(1,1),
(2,2),
(5,3),
(5,4),
(5,5),
(6,6),
(13,7),
(13,8),
(16,9),
(16,10);
INSERT INTO "BookCollection" VALUES
(3,1),
(10,2),
(14,1);
INSERT INTO "BookGroups" VALUES
(1,1),
(2,2),
(3,3),
(5,4),
(6,5),
(7,6),
(12,7),
(13,8);
INSERT INTO "BookList" VALUES
(9,1),
(10,1),
(11,1),
(12,1),
(13,1),
(14,1),
(15,1),
(16,1),
(17,1);
INSERT INTO "BookParody" VALUES
(1,1),
(2,2),
(5,3),
(6,4),
(6,5),
(13,6),
(16,7);
INSERT INTO "BookTag" VALUES
(1,1),
(1,2),
(1,3),
(1,4),
(1,5),
(1,6),
(1,7),
(1,8),
(1,9),
(1,10),
(1,11),
(1,12),
(1,13),
(1,14),
(2,15),
(2,16),
(2,17),
(2,9),
(2,18),
(3,19),
(3,1),
(3,20),
(3,15),
(3,21),
(3,22),
(3,7),
(3,23),
(3,24),
(3,25),
(3,26),
(3,9),
(3,27),
(3,28),
(3,29),
(3,30),
(3,31),
(3,32),
(4,20),
(4,33),
(4,34),
(4,3),
(4,35),
(4,4),
(4,36),
(4,7),
(4,37),
(4,9),
(4,11),
(4,38),
(4,39),
(5,21),
(5,40),
(5,41),
(5,3),
(5,42),
(5,43),
(5,44),
(5,45),
(5,7),
(5,46),
(5,47),
(5,9),
(5,48),
(6,19),
(6,49),
(6,50),
(6,51),
(6,7),
(6,9),
(6,27),
(6,52),
(6,13),
(7,53),
(7,44),
(7,8),
(7,54),
(7,55),
(8,1),
(8,20),
(8,15),
(8,56),
(8,57),
(8,58),
(8,50),
(8,7),
(8,24),
(8,9),
(8,59),
(8,52),
(8,60),
(9,19),
(9,1),
(9,15),
(9,61),
(9,62),
(9,63),
(9,64),
(9,9),
(9,65),
(9,66),
(9,67),
(9,18),
(10,19),
(10,68),
(10,57),
(10,17),
(10,69),
(10,70),
(10,61),
(10,25),
(10,9),
(10,28),
(10,71),
(10,72),
(11,19),
(11,73),
(11,74),
(11,57),
(11,75),
(11,69),
(11,76),
(11,42),
(11,43),
(11,44),
(11,7),
(11,9),
(12,1),
(12,68),
(12,20),
(12,57),
(12,75),
(12,77),
(12,78),
(12,3),
(12,45),
(12,61),
(12,7),
(12,9),
(12,48),
(12,38),
(12,12),
(12,79),
(13,80),
(13,15),
(13,81),
(13,7),
(13,9),
(13,82),
(13,72),
(14,19),
(14,1),
(14,21),
(14,7),
(14,83),
(14,26),
(14,84),
(14,9),
(14,85),
(14,11),
(14,28),
(14,67),
(14,18),
(15,19),
(15,15),
(15,3),
(15,36),
(15,6),
(15,61),
(15,7),
(15,9),
(15,86),
(15,31),
(16,19),
(16,15),
(16,81),
(16,50),
(16,87),
(16,24),
(16,88),
(16,72),
(17,19),
(17,89),
(17,68),
(17,20),
(17,80),
(17,15),
(17,33),
(17,57),
(17,3),
(17,36),
(17,70),
(17,61),
(17,90),
(17,7),
(17,25),
(17,9),
(17,91),
(17,59),
(17,82),
(17,31),
(17,32),
(17,92);
INSERT INTO "Books" VALUES
(1,'Shukujo no Tashinami | The Lady''s Taste','淑女のたしなみ',1,24,1,NULL,NULL,NULL,'2018-10-24',0),
(2,'Kinoko Matsuri | Mushroom Festival','キノコ祭',1,26,1,NULL,NULL,NULL,'2018-10-24',0),
(3,'Dolls -Yoshino Izumi Hen- | Dolls -Yoshino Izumi''s Story- Ch. 2','ドールズ -芳乃泉編- Ch. 2',1,25,1,23,NULL,NULL,'2018-11-14',0),
(4,'Sore wa Kurokute Suketeita | What’s Tight and Black and Sheer All Over?','それは黒くて透けていた',1,25,1,NULL,NULL,NULL,'2018-10-24',0),
(5,'Top Princess Bottom Princess','攻め姫受け姫',1,19,1,NULL,NULL,NULL,'2018-10-24',0),
(6,'Martina Onee-chan no Seikatsu | Big Sis Martina''s Sex Life','マルティナお姉ちゃんの性活',1,27,1,NULL,NULL,NULL,'2018-10-24',0),
(7,'Tanin ni Naru Kusuri | Medicine to Possess Another Person','他人になるクスリ',1,23,1,NULL,NULL,NULL,'2018-10-24',0),
(8,'Gyaru Ijime','ギャルいぢめ',1,21,1,NULL,NULL,NULL,'2018-10-24',0),
(9,'Toretate Amapetit','とれたて♥甘プ痴',1,22,1,NULL,NULL,NULL,'2018-10-24',0),
(10,'Takabisha Elf Kyousei Konin!! 3','高飛車エルフ強制婚姻!! 3',1,28,1,NULL,NULL,NULL,'2018-10-24',0),
(11,'Sono Shiroki Utsuwa ni Odei o Sosogu','その白き器に汚泥を注ぐ',1,20,1,NULL,NULL,NULL,'2018-10-24',0),
(12,'The Female Knight is brown and a 30 year old virgin, and on top of being a shotacon, she loves blonde princes.','女騎士は褐色で三十路処女ショタコンの上、金髪王子がお好き。',1,27,1,NULL,NULL,NULL,'2018-10-24',0),
(13,'Venus Nights',NULL,1,6,1,NULL,NULL,NULL,'2018-10-24',0),
(14,'Dolls Ch. 8','ドールズ 第8話',1,31,1,NULL,NULL,NULL,'2018-10-24',0),
(15,'Kangofu-san ni Kintama Sakusei Saremashita','看護婦さんにキンタマ搾精されました',1,23,1,NULL,NULL,NULL,'2018-10-24',0),
(16,'Futari no Futaba','フタリノフタバ',1,26,1,NULL,NULL,NULL,'2018-10-24',0),
(17,'Toshiue Zukushi Jukushita Sanshimai 1 -Hoshigari Miboujin to Ore- | The Three Older, Mature Sisters Next Door 1 -The Frustrated Widow and Me-','年上づくし熟した三姉妹1 -欲しがり未亡人と俺-',1,27,1,NULL,NULL,NULL,'2018-10-24',0);
INSERT INTO "Category" VALUES
(1,'Doujinshi'),
(2,'Manga');
INSERT INTO "Censorship" VALUES
(1,'Unknown'),
(2,'Censored'),
(3,'Decensored'),
(4,'Uncensored');
INSERT INTO "Character" VALUES
(1,'Darjeeling'),
(2,'Handler'),
(3,'Mario'),
(4,'Princess Peach'),
(5,'Super Crown Bowser | Bowsette'),
(6,'Martina'),
(7,'Momiji'),
(8,'Nyotengu'),
(9,'Akira Kurusu'),
(10,'Futaba Sakura');
INSERT INTO "Collection" VALUES
(1,'Dolls'),
(2,'Takabisha Elf Kyousei Konin!!');
INSERT INTO "ExternalInfo" VALUES
(1,1,43559,1,'2018-10-20','gezio',2,3.85,34,353,0,'2018-10-24',0),
(2,2,43551,1,'2018-10-20','MrOverlord12',3,4.67,55,709,0,'2018-10-24',0),
(3,3,43542,1,'2018-10-20','gezio',2,3.84,63,713,0,'2018-10-24',0),
(4,4,43528,1,'2018-10-18','Scarlet Spy',2,4.7,141,1180,0,'2018-10-24',0),
(5,5,43572,1,'2018-10-17','Scarlet Spy',2,4.23,101,1020,0,'2018-10-24',0),
(6,6,43516,1,'2018-10-17','Scarlet Spy',2,4.52,56,946,0,'2018-10-24',0),
(7,7,43538,1,'2018-10-18','MrOverlord12',2,3.8,69,694,0,'2018-10-24',0),
(8,8,43506,1,'2018-10-17','Scarlet Spy',2,4.23,92,1014,0,'2018-10-24',0),
(9,9,43455,1,'2018-10-11','DiceOL',2,4.69,237,2021,0,'2018-10-24',0),
(10,10,43454,1,'2018-10-11','DiceOL',2,4.15,84,823,0,'2018-10-24',0),
(11,11,43460,1,'2018-10-13','MrOverlord12',2,4.13,39,420,0,'2018-10-24',0),
(12,12,43445,1,'2018-10-11','Scarlet Spy',2,3.86,86,928,0,'2018-10-24',0),
(13,13,43432,1,'2018-10-11','gezio',2,3.76,34,532,0,'2018-10-24',0),
(14,14,43431,1,'2018-10-11','gezio',2,3.79,85,997,0,'2018-10-24',0),
(15,15,43419,1,'2018-10-10','gezio',2,4.33,106,1119,0,'2018-10-24',0),
(16,16,43453,1,'2018-10-11','DiceOL',2,4.49,81,930,0,'2018-10-24',0),
(17,17,43418,1,'2018-10-10','gezio',2,4.64,141,1857,0,'2018-10-24',0),
(18,16,43454,1,'2018-10-11','DiceOL',2,4.49,81,930,0,'2018-10-24',0);
INSERT INTO "Groups" VALUES
(1,'Kaiki Nisshoku'),
(2,'IRON GRIMOIRE'),
(3,'Fan no Hitori'),
(4,'SeaFox'),
(5,'Mousou Engine'),
(6,'Senpenbankashiki'),
(7,'Dokumushi Shokeitai'),
(8,'Maidoll');
INSERT INTO "Languages" VALUES
(1,'English');
INSERT INTO "List" VALUES
(1,'to-read');
INSERT INTO "MDB_Version" VALUES
(-1,0);
INSERT INTO "Parody" VALUES
(1,'Girls und Panzer / ガールズ&パンツァー'),
(2,'Monster Hunter World / モンスターハンター：ワールド'),
(3,'Super Mario Bros. / スーパーマリオブラザーズ'),
(4,'Dragon Quest / ドラゴンクエスト'),
(5,'Dragon Quest XI (11) / ドラゴンクエストXI'),
(6,'Dead or Alive / デッド・オア・アライブ'),
(7,'Persona 5 / ペルソナ5');
INSERT INTO "Sites" VALUES
(1,'tsumino.com');
INSERT INTO "Status" VALUES
(1,'Unknown'),
(2,'Ongoing'),
(3,'Completed'),
(4,'Unreleased'),
(5,'Hiatus');
INSERT INTO "Tag" VALUES
(1,'Anal'),
(2,'Chastity Belt'),
(3,'Femdom'),
(4,'Footjob'),
(5,'Gokkun'),
(6,'Handjob'),
(7,'Large Breasts'),
(8,'Masturbation'),
(9,'Nakadashi'),
(10,'Orgasm Denial'),
(11,'Pantyhose'),
(12,'Straight Shota'),
(13,'Sweating'),
(14,'Urethra Insertion'),
(15,'Blowjob'),
(16,'Decensored'),
(17,'Drugs'),
(18,'X-ray'),
(19,'Ahegao'),
(20,'Big Ass'),
(21,'Collar'),
(22,'Deepthroat'),
(23,'Leg Lock'),
(24,'Megane'),
(25,'MILF'),
(26,'Mind Break'),
(27,'Ponytail'),
(28,'Rape'),
(29,'Slave'),
(30,'Snuff'),
(31,'Symbol Shaped Pupils'),
(32,'Virginity (Male)'),
(33,'Cunnilingus'),
(34,'Face Sitting'),
(35,'Foot Fetish'),
(36,'Hairy'),
(37,'Licking'),
(38,'Short Hair'),
(39,'Smell'),
(40,'Dragon Girl'),
(41,'Fangs'),
(42,'Futa on Female'),
(43,'Futanari'),
(44,'Gender Bender'),
(45,'Hat'),
(46,'Leotard'),
(47,'Monster Girl'),
(48,'Royalty'),
(49,'Exhibitionism'),
(50,'Happy Sex'),
(51,'Impregnation'),
(52,'School Uniform'),
(53,'Fingering'),
(54,'Possession'),
(55,'Solo Action'),
(56,'Comedy'),
(57,'Dark Skin'),
(58,'Gyaru'),
(59,'Paizuri'),
(60,'Shared Senses'),
(61,'Huge Penis'),
(62,'Incest'),
(63,'Loli'),
(64,'Maledom'),
(65,'Niece'),
(66,'Slut'),
(67,'Stockings'),
(68,'Big Areola'),
(69,'Elf'),
(70,'Huge Breasts'),
(71,'Tattoo'),
(72,'Threesome'),
(73,'Body Swap'),
(74,'Bondage'),
(75,'Defloration'),
(76,'Filming'),
(77,'Double Penetration'),
(78,'Elder Sister'),
(79,'Tall Girl'),
(80,'Bikini'),
(81,'Group Sex'),
(82,'Swimsuit'),
(83,'Maid'),
(84,'Mind Control'),
(85,'Office Lady'),
(86,'Nurse'),
(87,'Layer Cake'),
(88,'Selfcest'),
(89,'BBW'),
(90,'Kimono / Yukata'),
(91,'Onsen'),
(92,'Widow');
CREATE UNIQUE INDEX "idx_artist_name" ON "Artist" (
	"name"
);
CREATE UNIQUE INDEX "idx_category_name" ON "Category" (
	"name"
);
CREATE UNIQUE INDEX "idx_character_name" ON "Character" (
	"name"
);
CREATE UNIQUE INDEX "idx_collection_name" ON "Collection" (
	"name"
);
CREATE UNIQUE INDEX "idx_groups_name" ON "Groups" (
	"name"
);
CREATE INDEX "idx_id_onpage_imported_from" ON "ExternalInfo" (
	"id_onpage",
	"imported_from"
);
CREATE UNIQUE INDEX "idx_list_name" ON "List" (
	"name"
);
CREATE UNIQUE INDEX "idx_parody_name" ON "Parody" (
	"name"
);
CREATE UNIQUE INDEX "idx_tag_name" ON "Tag" (
	"name"
);
CREATE UNIQUE INDEX "idx_title_eng_foreign" ON "Books" (
	"title_eng",
	"title_foreign"
);
CREATE TRIGGER set_books_last_change
                                     AFTER UPDATE ON Books
                                     BEGIN
                                        UPDATE Books
                                        SET last_change = DATE('now', 'localtime')
                                        WHERE id = NEW.id;
                                     END;
COMMIT;
PRAGMA foreign_keys=on;